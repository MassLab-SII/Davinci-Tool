"""MaaS (Model-as-a-Service) client for API interactions."""

import asyncio
import logging
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Callable
import httpx
from openai import AsyncOpenAI

from .utils.config import MaaSConfig, SingleModelConfig, DefaultConfig

logger = logging.getLogger(__name__)


class MaaSClient:
    """Client for interacting with MaaS (Model-as-a-Service)."""
    
    def __init__(self, config: MaaSConfig):
        """Initialize MaaS client.
        
        Args:
            config: MaaS configuration
        """
        self.config = config
        # Cache of API clients for different endpoints
        self._clients: Dict[str, AsyncOpenAI] = {}
        self._text_tool_endpoints: set[str] = set()
        # Optional observer hook for debugging/tracing model I/O.
        self._completion_observer: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_completion_observer(
        self, observer: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None:
        """Register a callback to receive completion request/response traces."""
        self._completion_observer = observer

    def _emit_completion_event(self, payload: Dict[str, Any]) -> None:
        observer = self._completion_observer
        if not observer:
            return
        try:
            observer(payload)
        except Exception as exc:
            logger.warning("Completion observer error: %s", exc)
        
    def _get_client(self, base_url: str, api_key: str) -> AsyncOpenAI:
        """Get or create an API client for a specific endpoint.
        
        Args:
            base_url: API base URL
            api_key: API key
            
        Returns:
            AsyncOpenAI client instance
        """
        cache_key = f"{base_url}|{api_key}"
        
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url
            )
            logger.debug(f"Created new API client for {base_url}")
            
        return self._clients[cache_key]

    @staticmethod
    def _as_namespace(value: Any) -> Any:
        """Convert nested response dictionaries into attribute-access objects."""
        if isinstance(value, dict):
            return SimpleNamespace(
                **{key: MaaSClient._as_namespace(val) for key, val in value.items()}
            )
        if isinstance(value, list):
            return [MaaSClient._as_namespace(item) for item in value]
        return value

    @staticmethod
    def _is_blocked_error(error: Exception) -> bool:
        """Return True for gateway blocks where a direct HTTP fallback is useful."""
        text = str(error).lower()
        return "request was blocked" in text or "403" in text or "forbidden" in text

    async def _create_completion_via_httpx(
        self,
        base_url: str,
        api_key: str,
        payload: Dict[str, Any],
        timeout: float,
    ) -> Any:
        """Call an OpenAI-compatible chat completions endpoint without the SDK.

        Some API gateways accept plain curl/httpx requests but block the OpenAI
        Python SDK request signature. This fallback keeps the request body
        identical to the SDK kwargs and converts the JSON response into the
        small attribute-access surface used by the collector.
        """
        url = base_url.rstrip("/") + "/chat/completions"
        request_body = dict(payload)
        extra_body = request_body.pop("extra_body", None)
        if isinstance(extra_body, dict):
            request_body.update(extra_body)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            response = await http_client.post(url, headers=headers, json=request_body)
        response.raise_for_status()
        data = response.json()
        return self._as_namespace(data)

    @staticmethod
    def _messages_for_text_tool_mode(
        messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert structured tool-call chat history into one plain user turn.

        Some gateways accept single-turn chat requests but fail on both native
        tools and ordinary multi-turn message arrays. Flattening preserves the
        transcript while keeping the wire format maximally simple.
        """
        transcript: List[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content")
            if role == "tool":
                tool_name = message.get("name") or message.get("tool_call_id") or "tool"
                transcript.append(f"TOOL RESULT from {tool_name}:\n{content or ''}")
                continue

            text_parts = []
            if content:
                text_parts.append(str(content))
            for call in message.get("tool_calls") or []:
                function = call.get("function", {}) if isinstance(call, dict) else {}
                text_parts.append(
                    "Previous tool call: "
                    + json.dumps(
                        {
                            "name": function.get("name"),
                            "arguments": function.get("arguments"),
                        },
                        ensure_ascii=False,
                    )
                )
            if text_parts:
                transcript.append(f"{role.upper()}:\n" + "\n".join(text_parts))

        tool_specs = []
        for tool in tools:
            function = tool.get("function", {}) if isinstance(tool, dict) else {}
            tool_specs.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters", {}),
                }
            )
        instruction = (
            "The API gateway does not support native structured tool calls. "
            "When you need to use a tool, output exactly one tool call in this format "
            "and do not add extra prose:\n"
            '<tool_call>{"name":"tool_name","arguments":{...}}</tool_call>\n\n'
            "Available tools:\n"
            + json.dumps(tool_specs, ensure_ascii=False, indent=2)
        )
        flattened = "Conversation transcript:\n\n" + "\n\n".join(transcript)
        return [{"role": "user", "content": flattened + "\n\n" + instruction}]

    async def _create_text_tool_completion_via_httpx(
        self,
        base_url: str,
        api_key: str,
        payload: Dict[str, Any],
        tools: List[Dict[str, Any]],
        timeout: float,
    ) -> Any:
        """Retry a tool request as plain text for gateways without tools support."""
        text_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"tools", "tool_choice", "extra_body"}
        }
        extra_body = payload.get("extra_body")
        if isinstance(extra_body, dict):
            text_payload.update(extra_body)
        text_payload["messages"] = self._messages_for_text_tool_mode(
            payload.get("messages", []), tools
        )
        return await self._create_completion_via_httpx(
            base_url=base_url,
            api_key=api_key,
            payload=text_payload,
            timeout=timeout,
        )

    async def _create_text_tool_completion_with_retries(
        self,
        base_url: str,
        api_key: str,
        payload: Dict[str, Any],
        tools: List[Dict[str, Any]],
        timeout: float,
        attempts: int = 3,
    ) -> Any:
        """Retry text-format tool calls through flaky OpenAI-compatible gateways."""
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                return await self._create_text_tool_completion_via_httpx(
                    base_url=base_url,
                    api_key=api_key,
                    payload=payload,
                    tools=tools,
                    timeout=timeout,
                )
            except Exception as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code not in {429, 500, 502, 503, 504} or attempt >= attempts:
                    break
                await asyncio.sleep(min(2.0, 0.4 * attempt))
        assert last_error is not None
        raise last_error
        
    def _get_model_config(self, model_config: SingleModelConfig) -> Dict[str, Any]:
        """Get effective configuration for a model (with defaults).
        
        Args:
            model_config: Single model configuration
            
        Returns:
            Dict with base_url, api_key, temperature, max_tokens
        """
        return {
            "model": model_config.model,
            "base_url": model_config.base_url or self.config.default.base_url,
            "api_key": model_config.api_key or self.config.default.api_key,
            "temperature": model_config.temperature or self.config.default.temperature,
            "max_tokens": model_config.max_tokens or self.config.default.max_tokens,
            "thinking": model_config.thinking,
            "reasoning_effort": model_config.reasoning_effort,
        }
        
    async def generate_completion(
        self,
        messages: List[Dict[str, Any]],
        model_config: SingleModelConfig,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """Generate a completion from the MaaS service.

        Args:
            messages: List of chat messages
            model_config: Model configuration (determines which endpoint to use)
            tools: Optional list of tools for function calling
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            timeout: Request timeout in seconds (default 120s)

        Returns:
            Completion response
        """
        # Get effective config
        effective_config = self._get_model_config(model_config)
        
        # Get the appropriate client
        client = self._get_client(
            effective_config["base_url"],
            effective_config["api_key"]
        )
        
        # Sanitize messages: OpenAI rejects empty tool_calls arrays
        clean_messages = []
        for msg in messages:
            tc = msg.get("tool_calls")
            if isinstance(tc, list) and len(tc) == 0:
                msg = {k: v for k, v in msg.items() if k != "tool_calls"}
            clean_messages.append(msg)

        kwargs = {
            "model": effective_config["model"],
            "messages": clean_messages,
            "temperature": temperature or effective_config["temperature"],
            "max_tokens": max_tokens or effective_config["max_tokens"]
        }
        if effective_config.get("thinking"):
            kwargs["extra_body"] = {
                "thinking": {"type": effective_config["thinking"]}
            }
        if effective_config.get("reasoning_effort"):
            kwargs["reasoning_effort"] = effective_config["reasoning_effort"]
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        logger.debug(f"Generating completion with model={kwargs['model']}, endpoint={effective_config['base_url']}, {len(messages)} messages")
        started_at = time.perf_counter()
        used_httpx_fallback = False
        endpoint_key = f"{effective_config['base_url']}|{kwargs['model']}"
        if tools and endpoint_key in self._text_tool_endpoints:
            response = await self._create_text_tool_completion_with_retries(
                base_url=effective_config["base_url"],
                api_key=effective_config["api_key"],
                payload=kwargs,
                tools=tools,
                timeout=timeout,
            )
            used_httpx_fallback = True
        else:
            try:
                response = await client.chat.completions.create(timeout=timeout, **kwargs)
            except Exception as e:
                if self._is_blocked_error(e):
                    logger.warning(
                        "OpenAI SDK request was blocked by %s; retrying once with direct httpx payload",
                        effective_config["base_url"],
                    )
                    try:
                        response = await self._create_completion_via_httpx(
                            base_url=effective_config["base_url"],
                            api_key=effective_config["api_key"],
                            payload=kwargs,
                            timeout=timeout,
                        )
                        used_httpx_fallback = True
                    except Exception as fallback_error:
                        if tools:
                            logger.warning(
                                "Direct structured tool request failed (%s); retrying as text-format tool call",
                                fallback_error,
                            )
                            self._text_tool_endpoints.add(endpoint_key)
                            try:
                                response = await self._create_text_tool_completion_with_retries(
                                    base_url=effective_config["base_url"],
                                    api_key=effective_config["api_key"],
                                    payload=kwargs,
                                    tools=tools,
                                    timeout=timeout,
                                )
                                used_httpx_fallback = True
                                fallback_error = None
                            except Exception as text_fallback_error:
                                fallback_error = text_fallback_error
                        if fallback_error is None:
                            pass
                        else:
                            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                            self._emit_completion_event(
                                {
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "model": kwargs["model"],
                                    "base_url": effective_config["base_url"],
                                    "temperature": kwargs["temperature"],
                                    "max_tokens": kwargs["max_tokens"],
                                    "messages": messages,
                                    "messages_count": len(messages),
                                    "request_chars": sum(
                                        len(str(m.get("content", ""))) for m in messages
                                    ),
                                    "tools_provided": bool(tools),
                                    "error": str(fallback_error),
                                    "sdk_error": str(e),
                                    "httpx_fallback": True,
                                    "latency_ms": elapsed_ms,
                                }
                            )
                            raise fallback_error from e
                else:
                    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                    self._emit_completion_event(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "model": kwargs["model"],
                            "base_url": effective_config["base_url"],
                            "temperature": kwargs["temperature"],
                            "max_tokens": kwargs["max_tokens"],
                            "messages": messages,
                            "messages_count": len(messages),
                            "request_chars": sum(
                                len(str(m.get("content", ""))) for m in messages
                            ),
                            "tools_provided": bool(tools),
                            "error": str(e),
                            "latency_ms": elapsed_ms,
                        }
                    )
                    raise
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        
        # Log detailed response format for debugging
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        content = getattr(message, "content", None)
        reasoning_content = getattr(message, "reasoning_content", None)
        if reasoning_content is None:
            reasoning_content = getattr(message, "model_extra", {}).get("reasoning_content")
        if reasoning_content is None:
            try:
                reasoning_content = message.model_dump().get("reasoning_content")
            except Exception:
                reasoning_content = None
        
        logger.debug(f"API Response Details:")
        logger.debug(f"  - Content present: {content is not None and len(str(content)) > 0}")
        logger.debug(f"  - Content length: {len(str(content)) if content else 0}")
        logger.debug(f"  - Tool calls present: {tool_calls is not None}")
        logger.debug(f"  - Tool calls count: {len(tool_calls) if tool_calls else 0}")
        logger.debug(f"  - Finish reason: {response.choices[0].finish_reason}")
        
        if content and tool_calls is None:
            # Check if content contains text-format tool calls
            if "<tool_call>" in str(content) or "<function_calls>" in str(content):
                logger.warning(f"⚠️  Model returned text-format tool calls in content instead of structured tool_calls")
                logger.debug(f"  Content preview: {str(content)[:500]}")
        
        if tool_calls:
            logger.debug(f"  Tool calls details:")
            for i, tc in enumerate(tool_calls):
                logger.debug(f"    [{i}] id={tc.id}, name={tc.function.name}, args_len={len(tc.function.arguments)}")
        
        result = {
            "content": content,
            "reasoning_content": reasoning_content,
            "tool_calls": tool_calls,
            "finish_reason": response.choices[0].finish_reason,
            "raw_response": response,  # Include raw response for debugging
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0)
            }
        }
        self._emit_completion_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": kwargs["model"],
                "base_url": effective_config["base_url"],
                "temperature": kwargs["temperature"],
                "max_tokens": kwargs["max_tokens"],
                "messages": messages,
                "messages_count": len(messages),
                "request_chars": sum(len(str(m.get("content", ""))) for m in messages),
                "tools_provided": bool(tools),
                "response_content": content or "",
                "response_chars": len(content or ""),
                "reasoning_chars": len(reasoning_content or ""),
                "tool_calls_count": len(tool_calls) if tool_calls else 0,
                "finish_reason": response.choices[0].finish_reason,
                "usage": result["usage"],
                "httpx_fallback": used_httpx_fallback,
                "latency_ms": elapsed_ms,
            }
        )
        return result
        
    async def generate_text(
        self,
        prompt: str,
        model_config: SingleModelConfig,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
    ) -> str:
        """Generate text from a prompt.

        Args:
            prompt: User prompt
            model_config: Model configuration (determines which endpoint to use)
            system_prompt: Optional system prompt
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            timeout: Request timeout in seconds (default 120s)

        Returns:
            Generated text
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        messages.append({"role": "user", "content": prompt})
        
        response = await self.generate_completion(
            messages=messages,
            model_config=model_config,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        return response["content"] or ""
