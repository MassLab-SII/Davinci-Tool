#!/usr/bin/env python3
"""
验证 JSON 数据集格式是否符合工具调用训练要求
支持 .json 和 .jsonl 两种格式
"""

import json
import argparse
import os
import sys


def verify_record(record, record_idx):
    """验证单条记录格式"""
    errors = []
    
    # 检查必需字段
    for field in ["messages", "tools"]:
        if field not in record:
            errors.append(f"记录[{record_idx}]: 缺少字段 '{field}'")
    
    # 检查 messages
    messages = record.get("messages", [])
    if not isinstance(messages, list):
        errors.append(f"记录[{record_idx}]: messages 应为列表")
        return errors
    
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            errors.append(f"记录[{record_idx}].messages[{i}]: 应为字典")
            continue
        
        # 检查 role 字段
        if "role" not in msg:
            errors.append(f"记录[{record_idx}].messages[{i}]: 缺少 'role' 字段")
        
        # 检查 tool role 的 content 类型（常见为字符串，也允许结构化对象）
        if msg.get("role") == "tool":
            content = msg.get("content")
            if content is not None and not isinstance(content, (str, dict, list)):
                errors.append(
                    f"记录[{record_idx}].messages[{i}]: tool content 应为字符串/字典/列表"
                )
        
        # 检查 assistant role 必须使用 tool_calls，而不是 function_call
        if msg.get("role") == "assistant":
            if "function_call" in msg:
                errors.append(f"记录[{record_idx}].messages[{i}]: assistant 不应包含 'function_call' 字段")
        
        # 检查 tool_calls 的 arguments 是否为字典或可解析为 JSON 对象的字符串
        tool_calls = msg.get("tool_calls", [])
        if tool_calls and not isinstance(tool_calls, list):
            errors.append(f"记录[{record_idx}].messages[{i}]: tool_calls 应为列表")
            continue
            
        for j, tc in enumerate(tool_calls):
            if not isinstance(tc, dict):
                errors.append(f"记录[{record_idx}].messages[{i}].tool_calls[{j}]: 应为字典")
                continue
            
            function = tc.get("function", {})
            if not isinstance(function, dict):
                errors.append(f"记录[{record_idx}].messages[{i}].tool_calls[{j}]: function 应为字典")
                continue
                
            args = function.get("arguments")
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    if not isinstance(parsed, dict):
                        errors.append(
                            f"记录[{record_idx}].messages[{i}].tool_calls[{j}]: arguments JSON 根元素应为对象"
                        )
                except json.JSONDecodeError:
                    errors.append(
                        f"记录[{record_idx}].messages[{i}].tool_calls[{j}]: arguments 字符串不是有效 JSON"
                    )
            elif args is not None and not isinstance(args, dict):
                errors.append(
                    f"记录[{record_idx}].messages[{i}].tool_calls[{j}]: arguments 应为字典或 JSON 字符串"
                )
    
    # 检查 tools 的 parameters 是否为字典或可解析为 JSON 对象的字符串
    tools = record.get("tools") or []
    if tools and not isinstance(tools, list):
        errors.append(f"记录[{record_idx}]: tools 应为列表")
        return errors
    
    for i, tool in enumerate(tools):
        if not isinstance(tool, dict):
            errors.append(f"记录[{record_idx}].tools[{i}]: 应为字典")
            continue
        
        function = tool.get("function", {})
        if not isinstance(function, dict):
            errors.append(f"记录[{record_idx}].tools[{i}]: function 应为字典")
            continue
            
        params = function.get("parameters")
        if isinstance(params, str):
            try:
                parsed = json.loads(params)
                if not isinstance(parsed, dict):
                    errors.append(
                        f"记录[{record_idx}].tools[{i}]: parameters JSON 根元素应为对象"
                    )
            except json.JSONDecodeError:
                errors.append(
                    f"记录[{record_idx}].tools[{i}]: parameters 字符串不是有效 JSON"
                )
        elif params is not None and not isinstance(params, dict):
            errors.append(f"记录[{record_idx}].tools[{i}]: parameters 应为字典或 JSON 字符串")
    
    return errors


def verify_json_file(file_path, max_errors=50, verbose=False):
    """验证 JSON 文件"""
    print(f"\n{'='*60}")
    print(f"验证文件: {file_path}")
    print(f"{'='*60}")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"❌ 错误: 文件不存在")
        return False
    
    # 获取文件大小
    file_size = os.path.getsize(file_path)
    print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
    
    # 判断文件格式
    is_jsonl = file_path.endswith('.jsonl')
    print(f"文件格式: {'JSONL' if is_jsonl else 'JSON'}")
    
    all_errors = []
    total_records = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            if is_jsonl:
                # JSONL 格式：逐行读取
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        total_records += 1
                        errors = verify_record(record, line_num)
                        all_errors.extend(errors)
                    except json.JSONDecodeError as e:
                        all_errors.append(f"第 {line_num} 行: JSON 解析错误 - {e}")
                    
                    if len(all_errors) >= max_errors:
                        print(f"⚠️ 错误数量已达上限 {max_errors}，停止检查")
                        break
            else:
                # JSON 格式：一次性加载
                data = json.load(f)
                
                if isinstance(data, list):
                    total_records = len(data)
                    print(f"记录总数: {total_records}")
                    
                    for idx, record in enumerate(data):
                        errors = verify_record(record, idx)
                        all_errors.extend(errors)
                        
                        if len(all_errors) >= max_errors:
                            print(f"⚠️ 错误数量已达上限 {max_errors}，停止检查")
                            break
                        
                        # 进度显示
                        if verbose and (idx + 1) % 10000 == 0:
                            print(f"  已检查 {idx + 1}/{total_records} 条记录...")
                elif isinstance(data, dict):
                    total_records = 1
                    errors = verify_record(data, 0)
                    all_errors.extend(errors)
                else:
                    all_errors.append("JSON 文件根元素应为列表或字典")
                    
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 读取文件错误: {e}")
        return False
    
    # 输出结果
    print(f"\n{'─'*40}")
    print(f"检查完成")
    print(f"  - 记录总数: {total_records}")
    print(f"  - 错误数量: {len(all_errors)}")
    
    if all_errors:
        print(f"\n❌ 发现以下错误:")
        for i, error in enumerate(all_errors[:max_errors], 1):
            print(f"  {i}. {error}")
        if len(all_errors) > max_errors:
            print(f"  ... 还有 {len(all_errors) - max_errors} 个错误未显示")
        return False
    else:
        print(f"\n✅ 验证通过！数据格式正确")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="验证 JSON/JSONL 数据集格式是否符合工具调用训练要求",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python verify_json.py data.json
  python verify_json.py data.jsonl --max-errors 100
  python verify_json.py data.json --verbose
        """
    )
    
    parser.add_argument(
        "file",
        type=str,
        help="要验证的 JSON 或 JSONL 文件路径"
    )
    
    parser.add_argument(
        "--max-errors",
        type=int,
        default=50,
        help="最多显示的错误数量 (默认: 50)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细进度信息"
    )
    
    args = parser.parse_args()
    
    # 执行验证
    success = verify_json_file(
        args.file,
        max_errors=args.max_errors,
        verbose=args.verbose
    )
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
