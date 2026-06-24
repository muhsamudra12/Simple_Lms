from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Sesuaikan dengan migration terakhir di folder migrations kamu
        ('tasks', '0009_alter_course_image_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nama_komentator', models.CharField(max_length=100, verbose_name='Nama')),
                ('isi_komentar', models.TextField(verbose_name='Komentar')),
                ('dibuat_pada', models.DateTimeField(auto_now_add=True, verbose_name='Waktu Komentar')),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='comments',
                    to='tasks.course'
                )),
            ],
            options={
                'verbose_name': 'Komentar',
                'verbose_name_plural': 'Daftar Komentar',
                'ordering': ['-dibuat_pada'],
            },
        ),
    ]