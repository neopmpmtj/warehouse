def can_manage_catalog(user):
    return user.is_authenticated and user.is_staff
