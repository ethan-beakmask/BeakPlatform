"""
FormWorkflow Module - OpSet Handler
變數設定節點處理器

負責變數設定與運算：數學運算、字串連接、變數轉換。
"""
import re
import ast
import operator
from typing import Dict, Any, Union
from .base import BaseNodeHandler


class OpSetHandler(BaseNodeHandler):
    """變數設定處理器"""

    # 安全的運算符對應
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def validate(self) -> bool:
        """驗證節點配置"""
        operations = self.get_config_value('operations')

        if not operations:
            self.log_info('OpSet 節點沒有配置 operations')
            return True

        if not isinstance(operations, list):
            raise ValueError('operations 必須是陣列')

        for idx, op in enumerate(operations):
            if not isinstance(op, dict):
                raise ValueError(f'operations[{idx}] 必須是物件')

            if 'target_var' not in op:
                raise ValueError(f'operations[{idx}] 缺少 target_var')

            if 'operation' not in op:
                raise ValueError(f'operations[{idx}] 缺少 operation')

            valid_ops = ['set', 'add', 'subtract', 'multiply', 'divide',
                        'concat', 'convert', 'increment', 'decrement', 'expr']
            if op['operation'] not in valid_ops:
                raise ValueError(f'operations[{idx}].operation 必須是: {", ".join(valid_ops)}')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理 OpSet 節點"""
        self.report_running()

        operations = self.get_config_value('operations')

        if not operations:
            return {
                'status': 'success',
                'message': 'OpSet 節點沒有配置操作',
                'data': {}
            }

        results = {}
        errors = []

        for idx, op in enumerate(operations):
            try:
                result = self._execute_operation(op)
                results[op['target_var']] = result

                # 儲存到工作流變數
                self.set_global_var(op['target_var'], result)

                self.log_info(f'變數操作完成: {op["target_var"]} = {result}', {
                    'operation': op['operation'],
                    'target_var': op['target_var'],
                    'result': result
                })
            except Exception as e:
                error_msg = f'操作 {idx} 失敗: {str(e)}'
                errors.append(error_msg)
                self.log_error(error_msg, {'operation': op})

        if errors:
            return {
                'status': 'success',  # 仍繼續流程
                'message': f'部分操作失敗: {len(errors)}/{len(operations)}',
                'data': {'results': results, 'errors': errors}
            }

        return {
            'status': 'success',
            'message': f'完成 {len(operations)} 個變數操作',
            'data': {'results': results}
        }

    def _execute_operation(self, op: Dict[str, Any]) -> Any:
        """執行單一操作"""
        operation = op['operation']
        target_var = op['target_var']

        if operation == 'set':
            return self._evaluate_value(op.get('value'))

        elif operation == 'add':
            current = self._get_var(target_var, 0)
            value = self._evaluate_value(op.get('value', 0))
            return self._format_number(float(current) + float(value))

        elif operation == 'subtract':
            current = self._get_var(target_var, 0)
            value = self._evaluate_value(op.get('value', 0))
            return self._format_number(float(current) - float(value))

        elif operation == 'multiply':
            current = self._get_var(target_var, 0)
            value = self._evaluate_value(op.get('value', 1))
            return self._format_number(float(current) * float(value))

        elif operation == 'divide':
            current = self._get_var(target_var, 0)
            value = self._evaluate_value(op.get('value', 1))
            if float(value) == 0:
                raise ValueError('除數不能為 0')
            return self._format_number(float(current) / float(value))

        elif operation == 'concat':
            current = self._get_var(target_var, '')
            value = self._evaluate_value(op.get('value', ''))
            return str(current) + str(value)

        elif operation == 'increment':
            current = self._get_var(target_var, 0)
            return self._format_number(float(current) + 1)

        elif operation == 'decrement':
            current = self._get_var(target_var, 0)
            return self._format_number(float(current) - 1)

        elif operation == 'convert':
            value = self._evaluate_value(op.get('value'))
            convert_to = op.get('convert_to', 'string')
            if convert_to == 'int':
                return int(float(value))
            elif convert_to == 'float':
                return float(value)
            elif convert_to == 'string':
                return str(value)
            elif convert_to == 'bool':
                return bool(value)
            else:
                raise ValueError(f'不支援的轉換類型: {convert_to}')

        elif operation == 'expr':
            expr_str = op.get('value', '')
            return self._evaluate_expression(expr_str)

        else:
            raise ValueError(f'未知的操作: {operation}')

    def _evaluate_value(self, value: Any) -> Any:
        """評估值，支援變數引用"""
        if value is None:
            return None

        if isinstance(value, str):
            def replace_var(match):
                var_name = match.group(1)
                return str(self._get_var(var_name, ''))

            value = re.sub(r'\$\{([^}]+)\}', replace_var, value)

            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                return value

        return value

    def _get_var(self, var_name: str, default: Any = None) -> Any:
        """取得變數值（使用 base handler 的變數服務）"""
        return self.get_var(var_name, default)

    def _format_number(self, value: float) -> Union[int, float]:
        """格式化數字"""
        if value == int(value):
            return int(value)
        return value

    def _evaluate_expression(self, expr_str: str) -> Union[int, float, str]:
        """安全地評估數學表達式"""
        if not expr_str or not expr_str.strip():
            raise ValueError('表達式不能為空')

        def replace_var(match):
            var_name = match.group(1)
            value = self._get_var(var_name, 0)
            try:
                return str(float(value))
            except (ValueError, TypeError):
                raise ValueError(f'變數 {var_name} 不是有效的數字')

        processed_expr = re.sub(r'\$\{([^}]+)\}', replace_var, expr_str)

        try:
            result = self._safe_eval(processed_expr)
            return self._format_number(result)
        except Exception as e:
            raise ValueError(f'表達式評估失敗: {str(e)}')

    def _safe_eval(self, expr_str: str) -> float:
        """使用 AST 安全評估數學表達式"""
        try:
            tree = ast.parse(expr_str, mode='eval')
        except SyntaxError as e:
            raise ValueError(f'語法錯誤: {str(e)}')

        return self._eval_node(tree.body)

    def _eval_node(self, node) -> float:
        """遞迴評估 AST 節點"""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f'不支援的常數類型')

        elif isinstance(node, ast.Num):
            return float(node.n)

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)

            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f'不支援的運算符')

            if op_type in (ast.Div, ast.FloorDiv) and right == 0:
                raise ValueError('除數不能為 0')

            return self.SAFE_OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)

            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f'不支援的一元運算符')

            return self.SAFE_OPERATORS[op_type](operand)

        elif isinstance(node, ast.Expression):
            return self._eval_node(node.body)

        else:
            raise ValueError(f'不支援的表達式類型')
