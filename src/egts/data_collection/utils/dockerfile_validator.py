"""
Dockerfile Validator and Auto-Fixer
====================================

Automatically validates and fixes common LLM-generated Dockerfile errors:
- Multi-line RUN echo commands without proper escaping
- Missing or incomplete instructions
- Invalid instruction names
- Unclosed quotes
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


class DockerfileValidator:
    """Validates and auto-fixes Dockerfile syntax errors."""
    
    VALID_INSTRUCTIONS = {
        'FROM', 'RUN', 'CMD', 'LABEL', 'EXPOSE', 'ENV', 'ADD', 'COPY',
        'ENTRYPOINT', 'VOLUME', 'USER', 'WORKDIR', 'ARG', 'ONBUILD',
        'STOPSIGNAL', 'HEALTHCHECK', 'SHELL'
    }
    
    def __init__(self):
        self.fixes_applied = []
    
    def validate_and_fix(self, dockerfile: str) -> Tuple[str, List[str]]:
        """Validate and auto-fix Dockerfile.
        
        Args:
            dockerfile: Raw Dockerfile content
            
        Returns:
            Tuple of (fixed_dockerfile, list_of_fixes_applied)
        """
        self.fixes_applied = []
        
        # Step 1: Remove markdown code fences
        dockerfile = self._remove_code_fences(dockerfile)
        
        # Step 2: Fix multi-line RUN commands
        dockerfile = self._fix_multiline_run_commands(dockerfile)
        
        # Step 3: Remove invalid/incomplete commands
        dockerfile = self._remove_invalid_commands(dockerfile)
        
        # Step 4: Validate final result
        self._validate_syntax(dockerfile)
        
        return dockerfile, self.fixes_applied
    
    def _remove_code_fences(self, dockerfile: str) -> str:
        """Remove markdown code fences if present."""
        dockerfile = dockerfile.strip()
        if dockerfile.startswith('```'):
            lines = dockerfile.split('\n')
            if lines[0].strip().startswith('```'):
                lines = lines[1:]
                self.fixes_applied.append("Removed opening code fence")
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
                self.fixes_applied.append("Removed closing code fence")
            dockerfile = '\n'.join(lines)
        return dockerfile
    
    def _fix_multiline_run_commands(self, dockerfile: str) -> str:
        """Fix multi-line RUN echo commands by merging and escaping properly.
        
        This is the main fix for the 'unknown instruction' errors.
        """
        lines = dockerfile.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                fixed_lines.append(line)
                i += 1
                continue
            
            # Check if this is a RUN command
            if line.strip().upper().startswith('RUN'):
                # Check if it contains echo with unclosed quote
                if 'echo' in line.lower():
                    fixed_line, lines_consumed = self._fix_run_echo(lines, i)
                    fixed_lines.append(fixed_line)
                    i += lines_consumed
                    continue
            
            fixed_lines.append(line)
            i += 1
        
        return '\n'.join(fixed_lines)
    
    def _fix_run_echo(self, lines: List[str], start_idx: int) -> Tuple[str, int]:
        """Fix a potentially multi-line RUN echo command.
        
        Returns:
            Tuple of (fixed_line, number_of_lines_consumed)
        """
        line = lines[start_idx]
        
        # Detect quote character used
        quote_chars = ["'", '"']
        quote_char = None
        for qc in quote_chars:
            if qc in line:
                quote_char = qc
                break
        
        if not quote_char:
            # No quotes, just return as is
            return line, 1
        
        # Count quotes in the first line
        quote_count = line.count(quote_char)
        
        # If quotes are balanced, no issue
        if quote_count % 2 == 0:
            return line, 1
        
        # Unclosed quote - need to collect following lines
        collected_lines = [line]
        current_idx = start_idx + 1
        
        while current_idx < len(lines):
            next_line = lines[current_idx].rstrip()
            
            # IMPORTANT: Don't skip empty lines - they are part of the content!
            # Only stop if we find:
            # 1. The closing quote
            # 2. A clear new Dockerfile instruction (but only if it's not on an empty/content line)
            
            # Check if we found the closing quote
            has_closing_quote = quote_char in next_line
            
            # Check if this line looks like a new Dockerfile instruction
            # BUT: empty lines and lines that don't start with uppercase words are content
            next_stripped = next_line.strip()
            is_new_instruction = False
            
            if next_stripped:  # Only check non-empty lines
                next_upper = next_stripped.upper()
                # Must start with a valid instruction AND be at the start of the line
                if any(next_upper.startswith(inst + ' ') or next_upper == inst 
                       for inst in self.VALID_INSTRUCTIONS):
                    # This looks like a new instruction
                    # Only treat as new instruction if we already found a redirect (>)
                    # Otherwise, might just be content
                    if '>' in ' '.join(collected_lines):
                        is_new_instruction = True
                        break
            
            collected_lines.append(next_line)
            
            # If we found the closing quote, check for redirect and stop
            if has_closing_quote:
                # Check if redirect is on this line or next
                if '>' in next_line:
                    current_idx += 1
                    break
                # Check next line for redirect
                if current_idx + 1 < len(lines) and '>' in lines[current_idx + 1]:
                    collected_lines.append(lines[current_idx + 1].rstrip())
                    current_idx += 2
                    break
                # Quote closed, no redirect found
                current_idx += 1
                break
            
            current_idx += 1
        
        # Now merge the lines properly
        if len(collected_lines) > 1:
            merged = self._merge_multiline_echo(collected_lines, quote_char)
            lines_consumed = len(collected_lines)
            self.fixes_applied.append(f"Fixed multi-line RUN echo command ({len(collected_lines)} lines merged)")
            return merged, lines_consumed
        
        return line, 1
    
    def _merge_multiline_echo(self, lines: List[str], quote_char: str) -> str:
        """Merge multi-line echo content into a single line with proper escaping.
        
        Args:
            lines: List of lines to merge
            quote_char: The quote character used (' or ")
            
        Returns:
            Single merged line with proper \\n escaping
        """
        # Get the RUN echo part from first line
        first_line = lines[0]
        
        # Find where the actual content starts
        match = re.search(r'(RUN\s+echo\s+' + re.escape(quote_char) + r')(.*)$', first_line, re.IGNORECASE)
        if not match:
            # Fallback: just join with spaces
            return ' '.join(line.strip() for line in lines)
        
        prefix = match.group(1)  # "RUN echo '"
        first_content = match.group(2)  # Content after opening quote
        
        # Collect all content lines (excluding prefix and suffix)
        content_parts = []
        
        # Add first line content (might already contain closing quote and redirect)
        # Remove any trailing redirect from first line
        first_content_clean = re.sub(r'\s*' + re.escape(quote_char) + r'\s*>.*$', '', first_content)
        if first_content_clean:
            content_parts.append(first_content_clean)
        
        # Process middle and last lines
        redirect_path = None
        for i, line in enumerate(lines[1:], 1):
            line_stripped = line.strip()
            
            # Check if this line has the closing quote
            if quote_char in line_stripped:
                # Extract content before closing quote
                parts = line_stripped.split(quote_char, 1)
                content_before_quote = parts[0]
                
                if content_before_quote:
                    content_parts.append(content_before_quote)
                
                # Check for redirect after the quote
                if len(parts) > 1:
                    after_quote = parts[1].strip()
                    redirect_match = re.search(r'>\s*(.+)$', after_quote)
                    if redirect_match:
                        redirect_path = redirect_match.group(1).strip()
                        # Remove any trailing quote from redirect path
                        redirect_path = redirect_path.rstrip(quote_char)
                break
            else:
                # Middle line - just add as is (might be empty)
                content_parts.append(line_stripped)
        
        # If no redirect found yet, check the last line again for redirect without quote
        if not redirect_path:
            last_line = lines[-1].strip()
            redirect_match = re.search(r'>\s*(.+)$', last_line)
            if redirect_match:
                redirect_path = redirect_match.group(1).strip()
                redirect_path = redirect_path.rstrip(quote_char)
        
        # Join with \\n escape sequence
        merged_content = '\\n'.join(content_parts)
        
        # Reconstruct the line
        if redirect_path:
            result = f"{prefix}{merged_content}{quote_char} > {redirect_path}"
        else:
            # No redirect found, just close the quote
            result = f"{prefix}{merged_content}{quote_char}"
        
        return result
    
    def _remove_invalid_commands(self, dockerfile: str) -> str:
        """Remove invalid or incomplete commands."""
        lines = dockerfile.split('\n')
        valid_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Keep empty lines and comments
            if not line_stripped or line_stripped.startswith('#'):
                valid_lines.append(line)
                continue
            
            # Check for incomplete apt-get install
            if line_stripped.endswith('apt-get install -y') or line_stripped.endswith('apt-get install'):
                # No package specified
                self.fixes_applied.append(f"Removed incomplete command: {line_stripped}")
                continue
            
            # Check for other incomplete RUN commands
            if line_stripped == 'RUN':
                self.fixes_applied.append("Removed empty RUN command")
                continue
            
            valid_lines.append(line)
        
        return '\n'.join(valid_lines)
    
    def _validate_syntax(self, dockerfile: str):
        """Validate final Dockerfile syntax.
        
        Raises:
            ValueError: If Dockerfile has syntax errors
        """
        lines = dockerfile.strip().split('\n')
        
        if not lines:
            raise ValueError("Dockerfile is empty")
        
        # Check for FROM instruction
        has_from = False
        for line in lines:
            line_upper = line.strip().upper()
            if line_upper.startswith('FROM'):
                has_from = True
                break
        
        if not has_from:
            raise ValueError("Dockerfile must start with FROM instruction")
        
        # Validate each instruction
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Skip empty lines and comments
            if not line_stripped or line_stripped.startswith('#'):
                continue
            
            # Extract instruction
            parts = line_stripped.split(None, 1)
            if not parts:
                continue
            
            instruction = parts[0].upper()
            
            if instruction not in self.VALID_INSTRUCTIONS:
                raise ValueError(
                    f"Invalid Dockerfile instruction on line {i}: '{instruction}'\n"
                    f"Valid instructions: {', '.join(sorted(self.VALID_INSTRUCTIONS))}\n"
                    f"Line content: {line_stripped[:100]}"
                )
        
        logger.info(f"Dockerfile validation passed ({len(lines)} lines)")
