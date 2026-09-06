"""Describe whether a user may need proxy assignment coverage during an absence."""
from datetime import date

from app.services.proxy_assignment_service import has_covering_proxy


class ApproverExposureService:
    @staticmethod
    def describe(org, user, start_date: date, end_date: date) -> dict:
        """Return whether proxy assignment coverage should be suggested for a date range."""
        already_covered = has_covering_proxy(
            org.secure_code,
            user.secure_code,
            start_date,
            end_date,
        )
        pending_count = 0
        template_count = 0

        if not already_covered:
            pending_count, template_count = ApproverExposureService._approval_exposure_counts(
                org.secure_code,
                user.secure_code,
            )

        return {
            'needed': (pending_count > 0 or template_count > 0) and not already_covered,
            'already_covered': already_covered,
            'pending_count': pending_count,
            'template_count': template_count,
        }

    @staticmethod
    def _approval_exposure_counts(org_secure_code: str, user_secure_code: str) -> tuple[int, int]:
        try:
            from modules.form_workflow.models import FwNodeExecutionQueue, FwPublishedFormWorkflow
            from modules.form_workflow.services.task_authorizer import build_actor, is_pending_assignee
        except ImportError:
            return 0, 0

        actor = build_actor(user_secure_code, org_secure_code)
        tasks = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.org_secure_code == org_secure_code,
            FwNodeExecutionQueue.status == 'WAITING',
            FwNodeExecutionQueue.node_type.in_(('Approve', 'FormAdapter')),
            FwNodeExecutionQueue.is_deleted == False,  # noqa: E712
        ).all()
        pending_count = sum(
            1 for task in tasks
            if is_pending_assignee(task, user_secure_code, org_secure_code, actor)
        )

        published = FwPublishedFormWorkflow.query.filter(
            FwPublishedFormWorkflow.org_secure_code == org_secure_code,
            FwPublishedFormWorkflow.is_deleted == False,  # noqa: E712
            FwPublishedFormWorkflow.status == 'Published',
        ).all()
        template_count = sum(
            1 for workflow in published
            if ApproverExposureService._snapshot_mentions_actor(
                workflow.workflow_snapshot,
                user_secure_code,
                actor.get('role_codes') or set(),
            )
        )
        return pending_count, template_count

    @staticmethod
    def _snapshot_mentions_actor(snapshot, user_secure_code: str, role_codes: set) -> bool:
        """PF-247 後 ROLE 有單位範圍，這裡刻意只比對角色 sc 不比對單位。

        本函式只是「這個人可能是某些流程樣板的簽核者」的曝光提示，超集無害，
        精確判定在 task_authorizer。
        """
        if not isinstance(snapshot, dict):
            return False
        graph = snapshot.get('graph')
        if not isinstance(graph, dict):
            return False
        nodes = graph.get('nodes')
        if not isinstance(nodes, list):
            return False

        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get('type') not in ('Approve', 'FormAdapter'):
                continue
            config = node.get('config')
            if not isinstance(config, dict):
                continue
            assignee_type = config.get('assignee_type')
            assignee_value = config.get('assignee_value') or ''
            if assignee_type == 'USER':
                assignees = {
                    part.strip()
                    for part in str(assignee_value).split(',')
                    if part.strip()
                }
                if user_secure_code in assignees:
                    return True
            elif assignee_type == 'ROLE' and str(assignee_value).strip() in role_codes:
                return True
        return False
