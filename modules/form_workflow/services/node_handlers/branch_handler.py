"""
FormWorkflow Module - Branch Handler
條件分支節點處理器

根據變數條件決定流程去向，支援複合條件與多路徑並行執行。
"""
import re
from typing import Dict, Any, List, Union
from .base import BaseNodeHandler


class BranchHandler(BaseNodeHandler):
    """
    條件分支處理器

    配置格式：
    {
        "rules": [
            {
                "name": "規則1",
                "conditions": [
                    {
                        "variable": "${status}",
                        "operator": "==",
                        "value": "approved",
                        "logic": "AND"
                    }
                ],
                "target_edges": ["edge-1", "edge-2"],
                "target_nodes": ["node-A"]
            }
        ],
        "fallback": {
            "action": "log" | "route",
            "target_edge": "edge-error",
            "log_message": "無匹配規則"
        }
    }
    """

    # 支援的比較運算符
    OPERATORS = {
        '==': lambda a, b: str(a) == str(b),
        '!=': lambda a, b: str(a) != str(b),
        '>': lambda a, b: float(a) > float(b),
        '>=': lambda a, b: float(a) >= float(b),
        '<': lambda a, b: float(a) < float(b),
        '<=': lambda a, b: float(a) <= float(b),
        'contains': lambda a, b: str(b) in str(a),
        'not_contains': lambda a, b: str(b) not in str(a),
        'startswith': lambda a, b: str(a).startswith(str(b)),
        'endswith': lambda a, b: str(a).endswith(str(b)),
        'in': lambda a, b: str(a) in (b if isinstance(b, (list, tuple)) else [x.strip() for x in str(b).split(',')]),
        'not_in': lambda a, b: str(a) not in (b if isinstance(b, (list, tuple)) else [x.strip() for x in str(b).split(',')]),
        'empty': lambda a, b: not a or str(a).strip() == '',
        'not_empty': lambda a, b: a and str(a).strip() != '',
        'matches': lambda a, b: bool(re.match(str(b), str(a))),
    }

    def validate(self) -> bool:
        """驗證節點配置"""
        rules = self.get_config_value('rules')

        if not rules:
            self.log_info('Branch 節點沒有規則，將使用 fallback')
            return True

        if not isinstance(rules, list):
            raise ValueError('rules 必須是陣列')

        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(f'rules[{idx}] 必須是物件')

            if 'conditions' not in rule:
                raise ValueError(f'rules[{idx}] 缺少 conditions')

            conditions = rule['conditions']
            if not isinstance(conditions, list) or len(conditions) == 0:
                raise ValueError(f'rules[{idx}].conditions 必須是非空陣列')

            for cidx, cond in enumerate(conditions):
                if 'variable' not in cond:
                    raise ValueError(f'rules[{idx}].conditions[{cidx}] 缺少 variable')
                if 'operator' not in cond:
                    raise ValueError(f'rules[{idx}].conditions[{cidx}] 缺少 operator')
                if cond['operator'] not in self.OPERATORS:
                    raise ValueError(f'不支援的運算符: {cond["operator"]}')

            if not rule.get('target_edges') and not rule.get('target_nodes'):
                raise ValueError(f'rules[{idx}] 需要設定 target_edges 或 target_nodes')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理條件分支節點"""
        rules = self.get_config_value('rules', [])
        fallback = self.get_config_value('fallback', {'action': 'log'})

        self.log_info('Branch 節點開始評估', {
            'rules_count': len(rules)
        })

        matched_rules = []
        evaluation_results = []

        for idx, rule in enumerate(rules):
            try:
                is_match = self._evaluate_rule(rule)
                evaluation_results.append({
                    'rule_index': idx,
                    'rule_name': rule.get('name', f'規則{idx+1}'),
                    'matched': is_match
                })

                if is_match:
                    matched_rules.append(rule)
                    self.log_info(f'規則匹配: {rule.get("name", f"規則{idx+1}")}')

            except Exception as e:
                self.log_error(f'規則 {idx} 評估失敗: {str(e)}')
                evaluation_results.append({
                    'rule_index': idx,
                    'rule_name': rule.get('name', f'規則{idx+1}'),
                    'error': str(e)
                })

        if matched_rules:
            selected_edges = []
            selected_nodes = []

            for rule in matched_rules:
                edges = rule.get('target_edges', [])
                nodes = rule.get('target_nodes', [])

                if isinstance(edges, list):
                    selected_edges.extend(edges)
                elif edges:
                    selected_edges.append(edges)

                if isinstance(nodes, list):
                    selected_nodes.extend(nodes)
                elif nodes:
                    selected_nodes.append(nodes)

            selected_edges = list(set(selected_edges))
            selected_nodes = list(set(selected_nodes))

            return {
                'status': 'success',
                'message': f'Branch 匹配 {len(matched_rules)} 條規則',
                'data': {
                    'matched_rules': [r.get('name', f'規則{i}') for i, r in enumerate(matched_rules)],
                    'selected_edges': selected_edges,
                    'selected_nodes': selected_nodes,
                    'evaluations': evaluation_results
                }
            }
        else:
            return self._handle_fallback(fallback, evaluation_results)

    def _evaluate_rule(self, rule: Dict) -> bool:
        """評估單條規則"""
        conditions = rule.get('conditions', [])
        if not conditions:
            return True

        groups = []
        current_group = []

        for i, cond in enumerate(conditions):
            current_group.append(cond)
            logic = cond.get('logic', 'AND').upper()
            if logic == 'OR' or i == len(conditions) - 1:
                groups.append(current_group)
                current_group = []

        for group in groups:
            group_result = True
            for cond in group:
                if not self._evaluate_condition(cond):
                    group_result = False
                    break
            if group_result:
                return True

        return False

    def _evaluate_condition(self, condition: Dict) -> bool:
        """評估單一條件"""
        variable_expr = condition.get('variable', '')
        operator = condition.get('operator', '==')
        compare_value = condition.get('value', '')

        actual_value = self._resolve_value(variable_expr)

        if isinstance(compare_value, str) and '${' in compare_value:
            compare_value = self._resolve_value(compare_value)

        op_func = self.OPERATORS.get(operator)
        if not op_func:
            raise ValueError(f'不支援的運算符: {operator}')

        try:
            return op_func(actual_value, compare_value)
        except (ValueError, TypeError) as e:
            self.log_warning(f'條件比較失敗: {variable_expr} {operator} {compare_value}')
            return False

    def _resolve_value(self, expr: str) -> Any:
        """解析變數表達式"""
        if not isinstance(expr, str):
            return expr

        single_var_match = re.match(r'^\$\{([^}]+)\}$', expr.strip())
        if single_var_match:
            var_name = single_var_match.group(1)
            if var_name.startswith('form.'):
                return self.get_form_field(var_name[5:])
            # 查詢 workflow 變數（LOCAL → GLOBAL）
            return self.get_var(var_name, '')

        return self.replace_variables(expr)

    def _handle_fallback(self, fallback: Dict, evaluations: List) -> Dict[str, Any]:
        """處理無匹配的情況"""
        action = fallback.get('action', 'log')

        if action == 'route':
            target_edge = fallback.get('target_edge')
            target_node = fallback.get('target_node')

            if target_edge or target_node:
                selected_edges = [target_edge] if target_edge else []
                selected_nodes = [target_node] if target_node else []

                self.log_info('Branch 無匹配，路由至 fallback')

                return {
                    'status': 'success',
                    'message': 'Branch 無匹配，使用 fallback 路由',
                    'data': {
                        'matched_rules': [],
                        'fallback_used': True,
                        'selected_edges': selected_edges,
                        'selected_nodes': selected_nodes,
                        'evaluations': evaluations
                    }
                }

        log_message = fallback.get('log_message', '無匹配的分支條件')
        self.log_warning(f'Branch fallback: {log_message}')

        return {
            'status': 'success',
            'message': f'Branch 無匹配: {log_message}',
            'data': {
                'matched_rules': [],
                'fallback_used': True,
                'use_default_path': True,
                'evaluations': evaluations
            }
        }
