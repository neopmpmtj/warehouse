ACTIVE_BRANCH_SESSION_KEY = "active_branch_id"


def get_user_branches(user):
    return (
        user.branch_memberships.select_related("branch")
        .filter(branch__is_active=True)
        .order_by("branch__name")
    )


def get_active_branch(request, memberships=None):
    if not request.user.is_authenticated:
        return None

    branch_id = request.session.get(ACTIVE_BRANCH_SESSION_KEY)
    if branch_id is None:
        return None

    if memberships is None:
        memberships = get_user_branches(request.user)

    for membership in memberships:
        if membership.branch_id == branch_id:
            return membership.branch

    return None


def set_active_branch(request, branch):
    request.session[ACTIVE_BRANCH_SESSION_KEY] = branch.id


def clear_active_branch(request):
    request.session.pop(ACTIVE_BRANCH_SESSION_KEY, None)
