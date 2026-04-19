from .models import Users as CustomUsers


def user_role(request):
    role = None
    if request.user.is_authenticated:
        if request.user.is_superuser:
            role = 'admin'
        else:
            try:
                custom_user = CustomUsers.objects.filter(username=request.user.username).first()
                if custom_user and custom_user.role:
                    role = custom_user.role.strip().lower()
            except Exception:
                role = None

            if role not in ['admin', 'staff', 'user']:
                role = 'staff' if request.user.is_staff else 'user'
    return {'user_role': role}
