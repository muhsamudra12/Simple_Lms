from django.db import migrations
from django.contrib.auth.hashers import make_password, identify_hasher


def hash_plaintext_passwords(apps, schema_editor):
    """
    Sebelum perubahan ini, password user disimpan plain text. Migration ini
    meng-hash ulang semua password lama yang masih plain text supaya user
    yang sudah terdaftar tetap bisa login setelah AUTH diperketat.
    identify_hasher() dipakai sebagai penanda: kalau formatnya BUKAN hash
    yang dikenali Django (melempar ValueError), berarti itu masih plain
    text dan perlu di-hash.
    """
    User = apps.get_model('tasks', 'User')
    for user in User.objects.all():
        try:
            identify_hasher(user.password)
            # Sudah berupa hash yang valid, tidak perlu diapa-apakan.
        except ValueError:
            user.password = make_password(user.password)
            user.save(update_fields=['password'])


def reverse_noop(apps, schema_editor):
    # Tidak ada cara aman untuk "un-hash" password, jadi reverse migration
    # ini sengaja dibuat tidak melakukan apa-apa.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0014_alter_user_password'),
    ]

    operations = [
        migrations.RunPython(hash_plaintext_passwords, reverse_noop),
    ]
