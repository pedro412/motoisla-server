from rest_framework.permissions import BasePermission

from apps.accounts.models import UserRole


ROLE_CAPABILITIES = {
    UserRole.ADMIN: {
        "catalog.view",
        "catalog.manage",
        "inventory.view",
        "inventory.manage",
        "purchases.view",
        "purchases.manage",
        "imports.view",
        "imports.manage",
        "sales.view",
        "sales.create",
        "sales.confirm",
        "sales.void",
        "sales.void.own_window",
        "sales.discount.limit",
        "sales.discount.override",
        "layaway.manage",
        "investor.view.own",
        "ledger.view.own",
        "investor.manage",
        "ledger.manage",
        "metrics.view",
        "expenses.view",
        "expenses.manage",
    },
    UserRole.CASHIER: {
        "catalog.view",
        "inventory.view",
        "purchases.view",
        "imports.view",
        "imports.manage",
        "sales.view",
        "sales.create",
        "sales.confirm",
        "sales.void.own_window",
        "sales.discount.limit",
        "layaway.manage",
    },
    UserRole.INVESTOR: {
        "investor.view.own",
        "ledger.view.own",
        "catalog.view",
    },
}


class RolePermission(BasePermission):
    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        capability_map = getattr(view, "capability_map", {})
        action = getattr(view, "action", request.method.lower())
        required = capability_map.get(action) or capability_map.get(request.method.lower()) or set()
        if not required:
            return True

        user_role = self._resolve_role(request.user)
        user_caps = ROLE_CAPABILITIES.get(user_role, set())
        return all(cap in user_caps for cap in required)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_authenticated and getattr(request.user, "role", None) == UserRole.ADMIN
