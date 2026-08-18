from django.shortcuts import redirect
from django.urls import reverse

from logging_utils import get_logger

from .session import (
    ACTIVE_BRANCH_SESSION_KEY,
    get_active_branch,
    get_user_branches,
    set_active_branch,
)

logger = get_logger("centcompras.branches")

EXEMPT_PATH_PREFIXES = (
    "/accounts/",
    "/admin/",
    "/manage/",
    "/api/manage/",
    "/static/",
    "/service-worker.js",
)


class ActiveBranchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_branch = None

        if request.user.is_authenticated:
            memberships = list(get_user_branches(request.user))
            request.active_branch = get_active_branch(request, memberships)

            if not self._is_exempt(request.path):
                if not memberships:
                    if request.path != reverse("no_branch_access"):
                        logger.info(
                            "Redirecting user %s to no-branch page",
                            request.user.email,
                        )
                        return redirect("no_branch_access")
                elif len(memberships) == 1:
                    if request.session.get(ACTIVE_BRANCH_SESSION_KEY) != memberships[0].branch_id:
                        set_active_branch(request, memberships[0].branch)
                        request.active_branch = memberships[0].branch
                        logger.debug(
                            "Auto-selected branch %s for user %s",
                            memberships[0].branch.name,
                            request.user.email,
                        )
                elif request.active_branch is None and request.path != reverse("select_branch"):
                    logger.info(
                        "Redirecting user %s to branch picker",
                        request.user.email,
                    )
                    return redirect("select_branch")

        return self.get_response(request)

    def _is_exempt(self, path):
        return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)
