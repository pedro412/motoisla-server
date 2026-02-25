from apps.audit.models import AuditLog


def record_audit(*, actor, action, entity_type, entity_id, payload=None):
    AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload or {},
    )
