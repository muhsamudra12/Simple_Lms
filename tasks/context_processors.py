from .models import User


def current_user(request):
    """
    Context processor — supaya navbar di index.html/stats.html/detail.html
    bisa langsung cek status login (logged_in_user) tanpa setiap view harus
    manual mengirim context itu satu-satu.
    """
    user_id = request.session.get('user_id')
    if user_id:
        user = User.objects.filter(id=user_id).first()
        if user:
            return {'logged_in_user': user}
    return {'logged_in_user': None}
