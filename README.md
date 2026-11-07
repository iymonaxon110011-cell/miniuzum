# Uzum Market

Uzum Market uslubidagi, mahsulotlarni admin panelisiz boshqarish mumkin bo'lgan Django katalogi.

## Hisob va Google orqali kirish

`/register/` sahifasida hisob yarating, `/login/` orqali kiring va saytdagi **Chiqish** tugmasi bilan hisobdan chiqing. Login va ro‘yxatdan o‘tish sahifalaridagi **Google bilan davom etish** tugmasi Django admin panelidagi **Social applications** sozlamasidan foydalanadi; client ID yoki secretni `settings.py` ga yoki muhit o‘zgaruvchisiga yozish shart emas. Google’da tanlangan hisob emaili saytdagi hisob emaili bilan mos bo‘lsa, mavjud hisob ochiladi; yangi foydalanuvchi esa Google orqali ro‘yxatdan o‘tadi.

Admin panelida **Social applications** bo‘limida Google providerli Social Application yarating, Google Cloud OAuth client ID va secretni kiriting. Loyihada `django.contrib.sites` yoqilmagan, shuning uchun admin panelidagi **Sites** bo‘limi kerak emas: Social Application barcha hostlar uchun ishlaydi va `SITE_ID` sozlamasi talab qilinmaydi. Google Cloud redirect URI `http://127.0.0.1:8000/accounts/google/login/callback/` bo‘lishi kerak (productionda domeningizni kiriting).

## Hamyon va bildirishnomalar

Profil sahifasida karta qo‘shish/o‘chirish va balansni to‘ldirish so‘rovlari admin tasdig‘iga yuboriladi. Admin ularni dashboarddagi **Karta so‘rovlari** yoki **Balans so‘rovlari** bo‘limidan tasdiqlashi yoki rad etishi mumkin. Natija foydalanuvchiga sayt ochiq turganida bildirishnoma sifatida ko‘rinadi. Yuqoridagi ♪ tugmasini bosib bildirishnoma ovozini yoqing; brauzer ovozni foydalanuvchi harakatidan keyin ijro etadi.

## Avtomatik mahsulot takliflari

Saytga har kuni birinchi tashrif bo‘lganda, mavjud tasdiqlangan mahsulotlardan bitta demo taklif tayyorlanib dashboarddagi **Avtomatik takliflar** bo‘limiga tushadi. Taklif admin tasdiqlamaguncha katalogda ko‘rinmaydi; admin uni tahrirlashi, tasdiqlashi yoki rad etishi mumkin. Takliflar haqiqiy yangi mahsulotlar emas va nomi, narxi, rasmi hamda tavsifi tekshirilishi kerak.

Bu loyiha AI API kalitisiz ishlaydi: taklif katalogdagi mahsulot ma’lumotiga asoslangan demo namuna, generativ AI natijasi emas. Oddiy admin paneli va dashboard orqali mahsulotni qo‘lda qo‘shish odatdagidek ishlayveradi.

## Mahsulot sharhlari

Sharhni faqat tizimga kirgan, xaridi yakunlangan foydalanuvchi qoldira oladi. Har bir xaridor mahsulotga bir marta sharh yozadi; u dashboarddagi **Sharhlar** bo‘limi yoki admin panelida tasdiqlangandan keyingina mahsulot sahifasida ko‘rinadi. Tasdiqlangan sharhlar xaridori bilan birga ko‘rsatiladi. Tasdiqlangan haqiqiy sharhlar bo‘lmaganida sahifada dizayn uchun namuna matnlar chiqadi va ular haqiqiy xaridor fikri emasligi ochiq belgilanadi.

## Maqsadli aksiyalar

Dashboarddagi **Aksiyalar** bo‘limida aksiya bannerini muayyan turkumga yoki tasdiqlangan alohida mahsulotga yo‘naltiring. Xaridor bosh sahifadagi aksiya tugmasini bosganda tanlangan turkum katalogi yoki mahsulot sahifasi ochiladi. Mahsulot tanlansa, aksiya turkum tanlovidan ustun turadi; maqsad ko‘rsatilmasa, katalog ochiladi.

## Marketing funksiyalari

Dashboarddagi **Aksiyalar** bo‘limidan banner, mahsulot/turkum chegirmasi va vaqtli **Flash sale** yaratiladi. Boshlanish va tugash vaqtlarini kiritsangiz, aksiya shu oraliqda ishlaydi. Chegirma mahsulot kartasi, batafsil sahifa, savat va buyurtma rasmiylashtirishda hisobga olinadi; bir mahsulotga bir nechta aksiya mos kelsa, eng past narx tanlanadi. Mahsulotning o‘zida `Eski narx` bo‘lsa, u aksiya narxi ustiga yana qo‘shilmaydi.

**Promokodlar** bo‘limida foizli yoki belgilangan summali kod yarating; minimal buyurtma va foydalanish limitini, amal qilish sanalarini sozlash mumkin. Xaridor kodni buyurtma rasmiylashtirishda kiritadi. Har bir mijoz bir koddan bir marta foydalanadi; promokod mahsulot chegirmasi bilan birga qo‘llanmaydi. Xaridordan kod uchun pul yechilgandan so‘ng kod buyurtmaga bog‘lanadi.

Buyurtma dashboardda **Yakunlangan** holatiga o‘tganda, to‘langan summaning 5% i xaridor hamyoniga keshbek sifatida qo‘shiladi. Keshbek takroran berilmaydi. Bosh sahifadagi **Flash sale** bo‘limi amaldagi vaqtli takliflarni, **Sizga yoqishi mumkin** bo‘limi esa yaqinda ko‘rilgan turkumdagi xaridorgir mahsulotlarni ko‘rsatadi. Aksiya bannerlari avvalgidek dashboarddan boshqariladi.

## Ishga tushirish

Katalogda mahsulotlarni narxi bo‘yicha arzonidan qimmatiga yoki aksincha saralash, narx oralig‘i va brend bo‘yicha filtrlash mumkin. Brend mahsulot qo‘shish/tahrirlash formasida kiritiladi. Tizimga kirgan foydalanuvchilar yurak tugmasi orqali mahsulotlarni **Sevimlilar** ro‘yxatida saqlashi va yuqori menyudan ko‘rishi mumkin.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

Sayt `http://127.0.0.1:8000/` manzilida ochiladi. Birinchi migratsiya katalogga namuna mahsulotlarni ham qo'shadi. Yuqoridagi **Mahsulot qo'shish** tugmasi orqali yangi mahsulot kiriting; har bir kartadan narxini tahrirlash yoki mahsulotni o'chirish боломжтой.

Production serverga joylashda `DEBUG=False` bo‘lsa ham CSS, JavaScript va boshqa static fayllar WhiteNoise orqali tarqatiladi. Deploydan keyin har safar `python manage.py collectstatic --noinput` buyrug‘ini ishga tushiring; u fayllarni `STATIC_ROOT` (`staticfiles/`) papkasiga yig‘adi. Yuklangan mahsulot va aksiya rasmlari `/media/` manzilidan `MEDIA_ROOT` (`media/`) ichidan xizmat qilinadi; deployda ushbu papkani saqlanadigan diskka joylashtiring va zaxira nusxasini oling. Katta trafik uchun media fayllarni Nginx yoki object storage orqali tarqatish tavsiya etiladi. Production domeningizni `ALLOWED_HOSTS` sozlamasiga qo‘shing.