from .models import BranchMembership


def get_membership(user, branch):
    return BranchMembership.objects.filter(user=user, branch=branch).first()


def can_create_order(user, branch):
    membership = get_membership(user, branch)
    return membership is not None and membership.role in (
        BranchMembership.Role.ADMIN,
        BranchMembership.Role.MANAGER,
        BranchMembership.Role.USER,
    )


def can_edit_or_delete_order(user, branch):
    membership = get_membership(user, branch)
    return membership is not None and membership.role == BranchMembership.Role.ADMIN


def can_manage_branch_users(user, branch):
    membership = get_membership(user, branch)
    return membership is not None and membership.role == BranchMembership.Role.ADMIN
