#!/usr/bin/env python3
"""
BeakMask Specification Checker
規格檢查工具 - 確保程式碼符合設計規格

檢查項目：
1. AUTH-01: 所有路由都有認證 decorator
2. AUTH-02: 使用統一的認證 decorator
3. TENANT-01: 多租戶 Model 有 org_secure_code
4. TENANT-02: API 層使用 ResourceGateway
5. 檔案結構符合規範
"""
import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """檢查結果"""
    rule: str
    file: str
    line: int
    message: str
    severity: str = "ERROR"


@dataclass
class SpecCheckReport:
    """檢查報告"""
    errors: List[CheckResult] = field(default_factory=list)
    warnings: List[CheckResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0

    def add_error(self, result: CheckResult):
        self.errors.append(result)
        self.failed += 1

    def add_warning(self, result: CheckResult):
        result.severity = "WARNING"
        self.warnings.append(result)

    def add_pass(self):
        self.passed += 1

    @property
    def is_success(self) -> bool:
        return self.failed == 0


class RouteAuthChecker(ast.NodeVisitor):
    """檢查路由是否有認證 decorator"""

    VALID_AUTH_DECORATORS = {
        'public_route',
        'login_required',
        'admin_required',
        'system_admin_required',
        'permission_required',
    }

    def __init__(self, filename: str):
        self.filename = filename
        self.results: List[CheckResult] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Check if this is a route
        is_route = False
        has_auth_decorator = False

        for decorator in node.decorator_list:
            # Check for @bp.route or @app.route
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == 'route':
                        is_route = True
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr == 'route':
                    is_route = True

            # Check for auth decorators
            decorator_name = None
            if isinstance(decorator, ast.Name):
                decorator_name = decorator.id
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                decorator_name = decorator.func.id

            if decorator_name in self.VALID_AUTH_DECORATORS:
                has_auth_decorator = True

        if is_route and not has_auth_decorator:
            self.results.append(CheckResult(
                rule="AUTH-02",
                file=self.filename,
                line=node.lineno,
                message=f"Route '{node.name}' missing authentication decorator",
            ))

        self.generic_visit(node)


class ImportTracker(ast.NodeVisitor):
    """追蹤 import 語句，識別 Model 類別"""

    # 已知的 Model 類別名稱 (來自 models 模組)
    KNOWN_MODELS = {
        'User', 'Organization', 'Contract', 'Role',
        'OrganizationalUnit', 'Module', 'MenuItem', 'Page',
        'MenuPermission', 'JobLevel', 'JobFamily', 'JobTitle',
        'EmployeePosition', 'Delegation',
        'UserUnitAssignment', 'UserRoleAssignment',
    }

    # 已知的非 Model 類別 (避免誤報)
    KNOWN_NON_MODELS = {
        'request', 'session', 'g', 'current_app', 'Blueprint',
        'Flask', 'Response', 'jsonify', 'render_template',
        'redirect', 'url_for', 'flash', 'abort',
        'db', 'ResourceGateway', 'MenuService',
    }

    def __init__(self):
        self.imported_models: Set[str] = set()
        self.model_aliases: Dict[str, str] = {}  # alias -> original name

    def visit_Import(self, node: ast.Import):
        """處理 import xxx"""
        for alias in node.names:
            name = alias.asname or alias.name
            # import models 情況
            if 'models' in alias.name:
                # 標記整個 models 模組被導入
                self.imported_models.add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """處理 from xxx import yyy"""
        module = node.module or ''

        # from app.models import User, Organization
        # from ..models import User
        if 'models' in module or module.endswith('models'):
            for alias in node.names:
                original_name = alias.name
                import_name = alias.asname or alias.name

                if original_name == '*':
                    # from models import * -> 加入所有已知 Model
                    self.imported_models.update(self.KNOWN_MODELS)
                elif original_name in self.KNOWN_MODELS:
                    self.imported_models.add(import_name)
                    if alias.asname:
                        self.model_aliases[alias.asname] = original_name
                else:
                    # 未知的名稱，但來自 models，也視為 Model
                    self.imported_models.add(import_name)

        self.generic_visit(node)

    def is_model_name(self, name: str) -> bool:
        """判斷名稱是否為 Model 類別"""
        # 明確排除的非 Model
        if name in self.KNOWN_NON_MODELS:
            return False
        # 從 models 導入的
        if name in self.imported_models:
            return True
        # 已知的 Model 名稱 (即使沒有追蹤到 import)
        if name in self.KNOWN_MODELS:
            return True
        return False


class DirectQueryChecker(ast.NodeVisitor):
    """檢查 API 層是否直接查詢資料庫 (L2: 含 Import 追蹤)"""

    def __init__(self, filename: str, import_tracker: ImportTracker):
        self.filename = filename
        self.import_tracker = import_tracker
        self.results: List[CheckResult] = []
        self.in_route_func = False
        self.current_func_name = ""

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Check if this function has @route decorator
        was_in_route = self.in_route_func
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == 'route':
                        self.in_route_func = True
                        self.current_func_name = node.name

        self.generic_visit(node)
        self.in_route_func = was_in_route

    def visit_Attribute(self, node: ast.Attribute):
        if self.in_route_func and node.attr == 'query':
            # Check if it's Model.query
            if isinstance(node.value, ast.Name):
                name = node.value.id
                # L2: 只有確認是 Model 才報警
                if self.import_tracker.is_model_name(name):
                    self.results.append(CheckResult(
                        rule="TENANT-02",
                        file=self.filename,
                        line=node.lineno,
                        message=f"Direct model query '{name}.query' in route '{self.current_func_name}'. Use ResourceGateway instead",
                        severity="WARNING"
                    ))
            # 處理 models.User.query 的情況
            elif isinstance(node.value, ast.Attribute):
                if isinstance(node.value.value, ast.Name):
                    module_name = node.value.value.id
                    class_name = node.value.attr
                    if module_name in self.import_tracker.imported_models or 'model' in module_name.lower():
                        if class_name in ImportTracker.KNOWN_MODELS or class_name[0].isupper():
                            self.results.append(CheckResult(
                                rule="TENANT-02",
                                file=self.filename,
                                line=node.lineno,
                                message=f"Direct model query '{module_name}.{class_name}.query' in route '{self.current_func_name}'. Use ResourceGateway instead",
                                severity="WARNING"
                            ))

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """檢查 db.session.query(Model) 模式"""
        if self.in_route_func:
            # 檢查 db.session.query(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'query':
                if isinstance(node.func.value, ast.Attribute):
                    if node.func.value.attr == 'session':
                        # db.session.query(User)
                        for arg in node.args:
                            if isinstance(arg, ast.Name):
                                if self.import_tracker.is_model_name(arg.id):
                                    self.results.append(CheckResult(
                                        rule="TENANT-02",
                                        file=self.filename,
                                        line=node.lineno,
                                        message=f"Direct session query 'db.session.query({arg.id})' in route '{self.current_func_name}'. Use ResourceGateway instead",
                                        severity="WARNING"
                                    ))

        self.generic_visit(node)


class ModelTenantChecker(ast.NodeVisitor):
    """檢查 Model 是否有租戶欄位"""

    def __init__(self, filename: str):
        self.filename = filename
        self.results: List[CheckResult] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        # Check if this is a model class (inherits from db.Model or BaseModel)
        is_model = False
        is_tenant_aware = False
        has_org_secure_code = False

        for base in node.bases:
            base_name = ""
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr

            if base_name in ('Model', 'BaseModel', 'TenantBaseModel'):
                is_model = True
            if base_name == 'TenantBaseModel':
                is_tenant_aware = True

        if is_model:
            # Check for org_secure_code attribute
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == 'org_secure_code':
                            has_org_secure_code = True

            # Only warn if it's a regular model without tenant awareness
            if not is_tenant_aware and not has_org_secure_code:
                # Check if it's a base class
                if node.name not in ('BaseModel', 'TenantBaseModel', 'TimestampMixin', 'SoftDeleteMixin', 'SecureCodeMixin'):
                    self.results.append(CheckResult(
                        rule="TENANT-01",
                        file=self.filename,
                        line=node.lineno,
                        message=f"Model '{node.name}' should inherit from TenantBaseModel or have org_secure_code",
                        severity="WARNING"
                    ))

        self.generic_visit(node)


def check_file_structure(project_root: Path) -> List[CheckResult]:
    """檢查專案結構"""
    results = []
    required_dirs = [
        'backend/app/security',
        'backend/app/api',
        'backend/app/models',
        'backend/app/services',
        'backend/tests',
        '.semgrep',
        'scripts',
    ]

    required_files = [
        'backend/app/security/decorators.py',
        'backend/app/security/auth_interceptor.py',
        'backend/app/security/tenant_isolation.py',
        'backend/app/security/resource_gateway.py',
        '.semgrep/beakmask-security.yaml',
    ]

    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if not full_path.is_dir():
            results.append(CheckResult(
                rule="STRUCTURE",
                file=str(dir_path),
                line=0,
                message=f"Required directory missing: {dir_path}",
            ))

    for file_path in required_files:
        full_path = project_root / file_path
        if not full_path.is_file():
            results.append(CheckResult(
                rule="STRUCTURE",
                file=str(file_path),
                line=0,
                message=f"Required file missing: {file_path}",
            ))

    return results


def check_python_file(filepath: Path) -> List[CheckResult]:
    """檢查單一 Python 檔案"""
    results = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()

        tree = ast.parse(source)

        # Run checkers based on file location
        str_path = str(filepath)

        if '/api/' in str_path:
            # Check routes for auth decorators
            checker = RouteAuthChecker(str_path)
            checker.visit(tree)
            results.extend(checker.results)

            # L2: 先追蹤 import，再檢查直接查詢
            import_tracker = ImportTracker()
            import_tracker.visit(tree)

            # Check for direct queries (with import tracking)
            query_checker = DirectQueryChecker(str_path, import_tracker)
            query_checker.visit(tree)
            results.extend(query_checker.results)

        if '/models/' in str_path:
            # Check models for tenant awareness
            checker = ModelTenantChecker(str_path)
            checker.visit(tree)
            results.extend(checker.results)

    except SyntaxError as e:
        results.append(CheckResult(
            rule="SYNTAX",
            file=str(filepath),
            line=e.lineno or 0,
            message=f"Syntax error: {e.msg}",
        ))

    return results


def run_spec_check(project_root: str) -> SpecCheckReport:
    """執行完整的規格檢查"""
    report = SpecCheckReport()
    root = Path(project_root)

    # Check file structure
    structure_results = check_file_structure(root)
    for result in structure_results:
        report.add_error(result)

    # Check Python files
    backend_path = root / 'backend'
    if backend_path.exists():
        for py_file in backend_path.rglob('*.py'):
            # Skip test files and __pycache__
            if '__pycache__' in str(py_file) or '/tests/' in str(py_file):
                continue

            results = check_python_file(py_file)
            for result in results:
                if result.severity == "ERROR":
                    report.add_error(result)
                else:
                    report.add_warning(result)

            if not results:
                report.add_pass()

    return report


def print_report(report: SpecCheckReport):
    """印出檢查報告"""
    print("\n" + "=" * 60)
    print("BeakMask Specification Check Report")
    print("=" * 60)

    if report.errors:
        print(f"\n❌ ERRORS ({len(report.errors)}):")
        print("-" * 40)
        for error in report.errors:
            print(f"  [{error.rule}] {error.file}:{error.line}")
            print(f"    {error.message}")

    if report.warnings:
        print(f"\n⚠️  WARNINGS ({len(report.warnings)}):")
        print("-" * 40)
        for warning in report.warnings:
            print(f"  [{warning.rule}] {warning.file}:{warning.line}")
            print(f"    {warning.message}")

    print("\n" + "-" * 40)
    print(f"Passed: {report.passed} | Failed: {report.failed} | Warnings: {len(report.warnings)}")

    if report.is_success:
        print("\n✅ All specification checks passed!")
    else:
        print("\n❌ Specification check failed!")

    print("=" * 60 + "\n")


def main():
    """主程式"""
    # Get project root from argument or use current directory
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = os.getcwd()

    print(f"Checking project: {project_root}")

    report = run_spec_check(project_root)
    print_report(report)

    # Exit with error code if check failed
    sys.exit(0 if report.is_success else 1)


if __name__ == '__main__':
    main()
