from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from logging_utils import get_logger

from .session import get_user_branches, set_active_branch

logger = get_logger("centcompras.branches")


@login_required
def select_branch(request):
    memberships = list(get_user_branches(request.user))

    if not memberships:
        return redirect("no_branch_access")

    if len(memberships) == 1:
        set_active_branch(request, memberships[0].branch)
        return redirect("product_page")

    if request.method == "POST":
        branch_id = request.POST.get("branch_id")
        for membership in memberships:
            if str(membership.branch_id) == branch_id:
                set_active_branch(request, membership.branch)
                logger.info(
                    "User %s selected branch %s",
                    request.user.email,
                    membership.branch.name,
                )
                return redirect("product_page")
        logger.warning(
            "User %s submitted invalid branch_id=%s",
            request.user.email,
            branch_id,
        )
        return HttpResponseForbidden("Invalid branch selection.")

    return render(
        request,
        "branches/select_branch.html",
        {"memberships": memberships},
    )


@login_required
def no_branch_access(request):
    return render(request, "branches/no_branch_access.html")
