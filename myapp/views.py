from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Sum, F, Q, Count
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from .models import Bills, Owners, Pets, Appointments, Treatments, Veterinarians, Species, MedicalRecords, Medicines, MedicineStock, PaymentMethod, AppointmentStatus, Suppliers, MedicineStockTransaction, POSTransaction, Users as CustomUsers
from .forms import OwnerForm
from datetime import date, datetime, timedelta
from django.utils import timezone
from dateutil.relativedelta import relativedelta
import calendar
import uuid
import os
from decimal import Decimal, InvalidOperation
from django.conf import settings
from functools import wraps


# Role helper functions

def get_user_role(request):
    if not request.user.is_authenticated:
        return None

    # priority: superuser -> custom role -> user
    if request.user.is_superuser:
        return 'admin'

    role = None
    try:
        custom_user = CustomUsers.objects.filter(username=request.user.username).first()
        if custom_user and custom_user.role:
            role = custom_user.role.strip().lower()
    except Exception:
        role = None

    if role in ['admin', 'user']:
        return role

    return 'user'


def require_admin(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        role = get_user_role(request)
        if role == 'admin':
            return view_func(request, *args, **kwargs)

        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่มีสิทธิ์เข้าถึง',
            'error_message': 'คุณไม่มีสิทธิ์ในการเข้าถึงหน้านี้',
            'error_reason': 'เฉพาะผู้ดูแลระบบ (Admin) เท่านั้นที่สามารถเข้าถึงหน้านี้'
        })
    return wrapped_view


def require_staff_or_admin(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        role = get_user_role(request)
        if role in ['admin', 'staff']:
            return view_func(request, *args, **kwargs)

        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่มีสิทธิ์เข้าถึง',
            'error_message': 'คุณไม่มีสิทธิ์ในการเข้าถึงหน้านี้',
            'error_reason': 'เฉพาะผู้ดูแลระบบ (Admin) และพนักงาน (Staff) เท่านั้นที่สามารถเข้าถึงหน้านี้'
        })
    return wrapped_view


def forbid_user_role(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        role = get_user_role(request)
        if role == 'user':
            return render(request, 'error_delete.html', {
                'error_title': '❌ ไม่มีสิทธิ์ทำรายการ',
                'error_message': 'บัญชีของคุณเป็น user และไม่มีสิทธิ์ในการทำรายการนี้',
                'error_reason': 'เฉพาะผู้ดูแลระบบ (Admin) เท่านั้นที่สามารถทำรายการได้'
            })

        return view_func(request, *args, **kwargs)
    return wrapped_view


# Decorator for admin access control
def admin_required(view_func):
    """Decorator to check if user is admin before accessing the view"""
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        # Check if user is superuser or admin
        if request.user.is_superuser or request.user.is_staff:
            return view_func(request, *args, **kwargs)

        # Check in CustomUsers table if role is admin
        try:
            custom_user = CustomUsers.objects.get(username=request.user.username)
            if custom_user.role and custom_user.role.lower() == 'admin':
                return view_func(request, *args, **kwargs)
        except CustomUsers.DoesNotExist:
            pass

        # If not admin, redirect to error page
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่มีสิทธิ์เข้าถึง',
            'error_message': 'คุณไม่มีสิทธิ์ในการเข้าถึงหน้านี้',
            'error_reason': 'เฉพาะผู้ดูแลระบบ (Admin) เท่านั้นที่สามารถเข้าถึงหน้าบริหารผู้ใช้งาน'
        })
    return wrapped_view


def get_next_id(model, field_name, prefix, width=3):
    from django.db import transaction
    with transaction.atomic():
        latest = model.objects.filter(**{f"{field_name}__startswith": prefix}).order_by(f"-{field_name}").first()
        if not latest:
            num = 1
        else:
            current = getattr(latest, field_name) or ""
            try:
                num = int(current.replace(prefix, "")) + 1
            except Exception:
                num = 1
        
        # Keep trying until we find an available ID
        while True:
            candidate_id = f"{prefix}{num:0{width}d}"
            if not model.objects.filter(**{field_name: candidate_id}).exists():
                return candidate_id
            num += 1


def get_next_bill_id(prefix='B', width=3):
    latest_bill = Bills.objects.filter(bill_id__startswith=prefix).order_by('-bill_id').first()
    latest_pos_bill = POSTransaction.objects.filter(bill_id__startswith=prefix).order_by('-bill_id').first()

    candidates = []
    if latest_bill:
        candidates.append(latest_bill.bill_id)
    if latest_pos_bill:
        candidates.append(latest_pos_bill.bill_id)

    if not candidates:
        num = 1
    else:
        latest = max(candidates)
        try:
            num = int(latest.replace(prefix, '')) + 1
        except Exception:
            num = 1

    return f"{prefix}{num:0{width}d}"


def reconcile_stock_from_transactions():
    # Sync MedicineStock quantity with sum of MedicineStockTransaction
    tx_sums = MedicineStockTransaction.objects.values('medicine_id').annotate(total=Sum('quantity_change'))
    for row in tx_sums:
        med_id = row['medicine_id']
        qty = row['total'] or 0
        stock = MedicineStock.objects.filter(medicine_id=med_id).first()
        if stock:
            if stock.quantity != qty:
                stock.quantity = qty
                stock.save()
        else:
            MedicineStock.objects.create(
                stock_id=str(uuid.uuid4())[:6],
                medicine_id=med_id,
                quantity=qty
            )


@login_required
def dashboard(request):
    total_revenue = Bills.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    # Show only active scheduled appointments (not completed/cancelled)
    scheduled = Appointments.objects.filter(status__status_name='Scheduled').count()
    active_appointments = Appointments.objects.exclude(status__status_name__in=['Completed', 'Cancelled']).count()
    completed = Appointments.objects.filter(status__status_name='Completed').count()
    cancelled = Appointments.objects.filter(status__status_name='Cancelled').count()

    # Most used medicines (shifted from report to dashboard as requested)
    most_used = Treatments.objects.values('medicine__medicine_name').annotate(total_qty=Sum('quantity')).order_by('-total_qty')[:5]

    # Stock summary for dashboard
    stock_rows = MedicineStock.objects.select_related('medicine').all()
    total_stock = stock_rows.aggregate(total_stock=Sum('quantity'))['total_stock'] or 0
    low_count = stock_rows.filter(quantity__lt=10).count()
    ok_count = stock_rows.filter(quantity__gte=10).count()

    # Bill summary - ชำระแล้วและยังไม่ชำระ
    paid_bills = Bills.objects.filter(payment_method__isnull=False).select_related('record__pet__owner', 'payment_method')
    unpaid_bills = Bills.objects.filter(payment_method__isnull=True).select_related('record__pet__owner')

    # Calendar month view for appointments
    month = request.GET.get('month')
    year = request.GET.get('year')
    try:
        month = int(month) if month else date.today().month
        year = int(year) if year else date.today().year
    except ValueError:
        month = date.today().month
        year = date.today().year

    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    month_days = cal.monthdatescalendar(year, month)

    thai_month_names = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน','กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
    calendar_month_name = thai_month_names[month - 1] if 1 <= month <= 12 else ''

    query = Appointments.objects.filter(appointment_date__year=year, appointment_date__month=month)\
        .select_related('pet', 'vet', 'status')

    day_map = {}
    for app in query:
        key = app.appointment_date
        day_map.setdefault(key, []).append(app)

    calendar_grid = []
    for week in month_days:
        week_data = []
        for d in week:
            apps = day_map.get(d, [])
            counts = {'Scheduled': 0, 'Completed': 0, 'Cancelled': 0, 'Other': 0}
            for app in apps:
                status_name = (app.status.status_name if app.status else 'Other')
                if status_name == 'Scheduled':
                    counts['Scheduled'] += 1
                elif status_name == 'Completed':
                    counts['Completed'] += 1
                elif status_name == 'Cancelled':
                    counts['Cancelled'] += 1
                else:
                    counts['Other'] += 1
            week_data.append({'date': d, 'is_current_month': d.month == month, 'apps': apps, 'counts': counts})
        calendar_grid.append(week_data)

    next_month = (datetime(year, month, 1) + relativedelta(months=1)).date()
    prev_month = (datetime(year, month, 1) - relativedelta(months=1)).date()

    prev_month_name = thai_month_names[prev_month.month - 1]
    next_month_name = thai_month_names[next_month.month - 1]

    upcoming_appointments = Appointments.objects.filter(appointment_date__gte=date.today())\
        .select_related('pet', 'vet', 'status')\
        .order_by('appointment_date', 'appointment_time')[:10]

    return render(request, 'dashboard.html', {
        'total_owners': Owners.objects.count(),
        'total_pet': Pets.objects.count(),
        'scheduled_appointments': scheduled,
        'active_appointments': active_appointments,
        'completed_appointments': completed,
        'cancelled_appointments': cancelled,
        'total_revenue': total_revenue,
        'most_used': most_used,
        'total_stock': total_stock,
        'stock_low_count': low_count,
        'stock_ok_count': ok_count,
        'paid_bills_count': paid_bills.count(),
        'unpaid_bills_count': unpaid_bills.count(),
        'paid_bills': paid_bills[:10],
        'unpaid_bills': unpaid_bills[:10],
        'upcoming_appointments': upcoming_appointments,
        'calendar_grid': calendar_grid,
        'calendar_month': month,
        'calendar_month_name': calendar_month_name,
        'calendar_year': year,
        'prev_month': prev_month,
        'next_month': next_month,
        'prev_month_name': prev_month_name,
        'next_month_name': next_month_name,
    })


# OWNER
@login_required
def owner_list(request):
    q = request.GET.get('q')
    if q:
        owners = Owners.objects.filter(
            Q(owner_id__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(email__icontains=q) |
            Q(address__icontains=q)
        )
    else:
        owners = Owners.objects.all()
    return render(request, 'owners.html', {'owners': owners, 'q': q})


def safe_qs(qs):
    try:
        return list(qs)
    except Exception:
        return []


@login_required
def add_owner(request):
    if request.method == 'POST':
        form = OwnerForm(request.POST)
        print(f"DEBUG: Form is_valid = {form.is_valid()}")
        print(f"DEBUG: Form errors = {form.errors}")
        print(f"DEBUG: Form data = {form.cleaned_data if form.is_valid() else 'Form not valid'}")
        
        if form.is_valid():
            try:
                email = form.cleaned_data.get('email')
                email = email if email and email.strip() else None
                
                new_owner = Owners.objects.create(
                    owner_id=get_next_id(Owners, 'owner_id', 'OWN'),
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    phone=form.cleaned_data['phone'],
                    email=email,
                    address=form.cleaned_data['address']
                )
                print(f"DEBUG: Owner created successfully: {new_owner.owner_id}")
                return redirect('owner_list')
            except Exception as e:
                print(f"DEBUG: Exception occurred: {str(e)}")
                import traceback
                traceback.print_exc()
                # ถ้าเกิดข้อผิดพลาดในการบันทึก
                error_messages = [f"เกิดข้อผิดพลาดในการบันทึก: {str(e)}"]
                return render(request, 'add_owner.html', {
                    'form': form,
                    'error_messages': error_messages
                })
        else:
            # แสดง errors เป็น popup
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
            
            return render(request, 'add_owner.html', {
                'form': form,
                'error_messages': error_messages
            })
    
    else:
        form = OwnerForm()
    
    return render(request, 'add_owner.html', {'form': form})


@login_required
def edit_owner(request, id):
    owner = get_object_or_404(Owners, pk=id)
    if request.method == 'POST':
        form = OwnerForm(request.POST, instance=owner)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            email = email if email and email.strip() else None
            
            owner.first_name = form.cleaned_data['first_name']
            owner.last_name = form.cleaned_data['last_name']
            owner.phone = form.cleaned_data['phone']
            owner.email = email
            owner.address = form.cleaned_data['address']
            owner.save()
            return redirect('owner_list')
        else:
            # แสดง errors เป็น popup
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
            
            return render(request, 'edit_owner.html', {
                'form': form,
                'owner': owner,
                'error_messages': error_messages
            })
    
    else:
        form = OwnerForm(instance=owner)
    
    return render(request, 'edit_owner.html', {
        'form': form,
        'owner': owner,
    })


@login_required
@forbid_user_role
def delete_owner(request, id):
    try:
        owner = get_object_or_404(Owners, pk=id)
        # Check if owner has pets
        pet_count = Pets.objects.filter(owner_id=id).count()
        if pet_count > 0:
            return render(request, 'error_delete.html', {
                'reason': 'ลูกค้าคนนี้มีสัตว์เลี้ยงที่ลงทะเบียนอยู่',
                'details': f'ลูกค้านี้มี {pet_count} ตัวสัตว์เลี้ยง โปรดลบสัตว์เลี้ยงจากระบบก่อน'
            })
        owner.delete()
        return redirect('owner_list')
    except IntegrityError:
        return render(request, 'error_delete.html', {
            'reason': 'ไม่สามารถลบลูกค้าได้ เนื่องมีข้อมูลที่เกี่ยวข้องในระบบ',
            'details': 'โปรดตรวจสอบและลบข้อมูลที่เกี่ยวข้องก่อน'
        })


# VETERINARIANS
@login_required
def vet_list(request):
    q = request.GET.get('q')
    if q:
        vets = Veterinarians.objects.filter(
            Q(vet_name__icontains=q) |
            Q(specialization__icontains=q) |
            Q(phone__icontains=q)
        )
    else:
        vets = Veterinarians.objects.all()

    vet_rows = []
    for vet in vets:
        vet_rows.append({
            'vet': vet,
            'image_url': get_vet_image_url(vet.vet_id)
        })

    return render(request, 'veterinarians.html', {'vets': vet_rows, 'q': q})


@login_required
@forbid_user_role
def add_vet(request):
    specializations = ['สัตวแพทย์ชั้นหนึ่ง', 'สัตวแพทย์ชั้นสอง', 'นักเทคนิคการสัตวแพทย์', 'ผู้ช่วยสัตวแพทย์']
    if request.method == 'POST':
        new_vet_id = get_next_id(Veterinarians, 'vet_id', 'VET')
        Veterinarians.objects.create(
            vet_id=new_vet_id,
            vet_name=request.POST.get('vet_name'),
            specialization=request.POST.get('specialization'),
            phone=request.POST.get('phone')
        )
        if 'photo' in request.FILES:
            save_vet_image(new_vet_id, request.FILES['photo'])
        return redirect('vet_list')
    return render(request, 'add_vet.html', {'specializations': specializations})


@login_required
@forbid_user_role
def edit_vet(request, id):
    specializations = ['สัตวแพทย์ชั้นหนึ่ง', 'สัตวแพทย์ชั้นสอง', 'นักเทคนิคการสัตวแพทย์', 'ผู้ช่วยสัตวแพทย์']
    vet = get_object_or_404(Veterinarians, pk=id)
    if request.method == 'POST':
        vet.vet_name = request.POST.get('vet_name')
        vet.specialization = request.POST.get('specialization')
        vet.phone = request.POST.get('phone')
        vet.save()
        if 'photo' in request.FILES:
            save_vet_image(vet.vet_id, request.FILES['photo'])
        return redirect('vet_list')
    return render(request, 'edit_vet.html', {'vet': vet, 'specializations': specializations, 'image_url': get_vet_image_url(vet.vet_id)})


@login_required
@forbid_user_role
def delete_vet(request, id):
    try:
        vet = get_object_or_404(Veterinarians, pk=id)
        vet.delete()
        return redirect('vet_list')
    except IntegrityError:
        return render(request, 'error_delete.html', {
            'reason': 'ไม่สามารถลบแพทย์ได้ เนื่องมีข้อมูลที่เกี่ยวข้องในระบบ',
            'details': 'โปรดตรวจสอบข้อมูลการนัดหมายหรือประวัติการรักษาของแพทย์ก่อน'
        })


@login_required
def vet_profile(request, id):
    vet = get_object_or_404(Veterinarians, pk=id)
    total_appointments = Appointments.objects.filter(vet_id=id).count()
    upcoming_appointments = Appointments.objects.filter(vet_id=id, status__status_name__iexact='scheduled').count()
    completed_appointments = Appointments.objects.filter(vet_id=id, status__status_name__iexact='completed').count()
    canceled_appointments = Appointments.objects.filter(vet_id=id, status__status_name__iexact='cancelled').count()
    total_medical_records = MedicalRecords.objects.filter(vet_id=id).count()
    image_url = get_vet_image_url(vet.vet_id)

    context = {
        'vet': vet,
        'image_url': image_url,
        'total_appointments': total_appointments,
        'upcoming_appointments': upcoming_appointments,
        'completed_appointments': completed_appointments,
        'canceled_appointments': canceled_appointments,
        'total_medical_records': total_medical_records,
    }
    return render(request, 'vet_profile.html', context)


@login_required
def get_districts_by_province(request):
    province_id = request.GET.get('province_id')
    try:
        districts = list(Districts.objects.filter(province_id=province_id).values('district_id', 'district_name'))
    except Exception:
        districts = []
    return JsonResponse({'districts': districts})


@login_required
def get_subdistricts_by_district(request):
    district_id = request.GET.get('district_id')
    try:
        subdistricts = list(Subdistricts.objects.filter(district_id=district_id).values('subdistrict_id', 'subdistrict_name', 'postal_code'))
    except Exception:
        subdistricts = []
    return JsonResponse({'subdistricts': subdistricts})


# PET
def get_pet_image_url(pet_id):
    image_dir = os.path.join(settings.MEDIA_ROOT, 'pet_images')
    if not os.path.exists(image_dir):
        return None
    for ext in ['.jpg', '.jpeg', '.png', '.gif']:
        candidate = os.path.join(image_dir, f"{pet_id}{ext}")
        if os.path.exists(candidate):
            return settings.MEDIA_URL + f"pet_images/{pet_id}{ext}"
    return None


def save_pet_image(pet_id, uploaded_file):
    image_dir = os.path.join(settings.MEDIA_ROOT, 'pet_images')
    os.makedirs(image_dir, exist_ok=True)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
        ext = '.jpg'
    filename = f"{pet_id}{ext}"
    path = os.path.join(image_dir, filename)
    with open(path, 'wb+') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return f"{settings.MEDIA_URL}pet_images/{filename}"


def get_vet_image_url(vet_id):
    image_dir = os.path.join(settings.MEDIA_ROOT, 'vet_images')
    if not os.path.exists(image_dir):
        return None
    for ext in ['.jpg', '.jpeg', '.png', '.gif']:
        candidate = os.path.join(image_dir, f"{vet_id}{ext}")
        if os.path.exists(candidate):
            return settings.MEDIA_URL + f"vet_images/{vet_id}{ext}"
    return None


def save_vet_image(vet_id, uploaded_file):
    image_dir = os.path.join(settings.MEDIA_ROOT, 'vet_images')
    os.makedirs(image_dir, exist_ok=True)
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
        ext = '.jpg'
    filename = f"{vet_id}{ext}"
    path = os.path.join(image_dir, filename)
    with open(path, 'wb+') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return f"{settings.MEDIA_URL}vet_images/{filename}"


@login_required
def pet_list(request):
    q = request.GET.get('q')
    species_filter = request.GET.get('species')
    pets = Pets.objects.select_related('owner', 'species')
    if q:
        pets = pets.filter(
            Q(pet_id__icontains=q) |
            Q(pet_name__icontains=q) |
            Q(owner__first_name__icontains=q) |
            Q(owner__last_name__icontains=q) |
            Q(species__species_name__icontains=q) |
            Q(breed__icontains=q) |
            Q(gender__icontains=q) |
            Q(weight__icontains=q)
        )
    if species_filter:
        pets = pets.filter(species__species_id=species_filter)
    pets = pets.all()
    pet_rows = []
    for pet in pets:
        age_year = age_month = None
        age_text = '-'
        if pet.birth_date:
            diff = relativedelta(date.today(), pet.birth_date)
            age_year = diff.years
            age_month = diff.months
            age_text = f"{age_year} ปี {age_month} เดือน" if (age_year or age_month) else '0 ปี'

        pet_rows.append({
            'pet': pet,
            'age_year': age_year,
            'age_month': age_month,
            'age': age_text,
            'image_url': get_pet_image_url(pet.pet_id)
        })
    return render(request, 'pet.html', {
        'pet': pet_rows,
        'q': q,
        'species_list': Species.objects.all(),
        'species_filter': species_filter
    })


@login_required
def add_pet(request):
    owners = Owners.objects.all()
    species = Species.objects.all()

    if request.method == "POST":
        age_year = int(request.POST.get('age_year') or 0)
        age_month = int(request.POST.get('age_month') or 0)
        birth_date = date.today() - relativedelta(years=age_year, months=age_month)
        owner_id = request.POST.get('owner')
        species_id = request.POST.get('species')
        species_other = (request.POST.get('species_other') or '').strip()

        if not owner_id or not species_id:
            error = "Owner and species are required."
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'add_pet.html', {
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'error': error
            })

        if species_id == 'SP999':
            if not species_other:
                error = "กรุณาระบุชนิดสัตว์สำหรับ 'อื่นๆ'."
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'add_pet.html', {
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'error': error
                })
            species_obj = Species.objects.filter(species_name__iexact=species_other).first()
            if not species_obj:
                new_species_id = get_next_id(Species, 'species_id', 'SP')
                species_obj = Species.objects.create(
                    species_id=new_species_id,
                    species_name=species_other,
                    description='Added from pet form'
                )
        else:
            try:
                species_obj = Species.objects.get(species_id=species_id)
            except Species.DoesNotExist:
                error = "Selected species does not exist."
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'add_pet.html', {
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'error': error
                })

        try:
            owner = Owners.objects.get(owner_id=owner_id)
        except Owners.DoesNotExist:
            error = "Selected owner does not exist."
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'add_pet.html', {
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'error': error
            })

        raw_gender = request.POST.get('gender')
        gender = raw_gender if raw_gender in ['M', 'F'] else None

        weight_str = (request.POST.get('weight') or '').strip()
        weight = None
        if weight_str:
            try:
                weight = Decimal(weight_str)
            except (InvalidOperation, ValueError):
                error = "น้ำหนักต้องเป็นตัวเลข"
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'add_pet.html', {
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'error': error
                })

            if weight <= 0:
                error = "น้ำหนักต้องมากกว่า 0"
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'add_pet.html', {
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'error': error
                })

            if weight > Decimal('999.99'):
                error = "น้ำหนักต้องไม่เกิน 999.99 กิโลกรัม (จำกัดตาม schema)" 
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'add_pet.html', {
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'error': error
                })

        try:
            pet = Pets.objects.create(
                pet_id=get_next_id(Pets, 'pet_id', 'PET'),
                owner=owner,
                species=species_obj,
                pet_name=request.POST.get('pet_name'),
                breed=request.POST.get('breed'),
                gender=gender,
                birth_date=birth_date,
                weight=weight
            )
            if 'pet_image' in request.FILES:
                save_pet_image(pet.pet_id, request.FILES['pet_image'])
            return redirect('pet_list')
        except (IntegrityError, InvalidOperation):
            error = "ไม่สามารถบันทึกน้ำหนัก พยายามใช้ค่า 0-1000"
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'add_pet.html', {
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'error': error
            })

    years = list(range(0, 25))
    months = list(range(0, 12))
    return render(request, 'add_pet.html', {'owners': owners, 'species': species, 'years': years, 'months': months})


@login_required
def edit_pet(request, id):
    pet = get_object_or_404(Pets, pk=id)
    owners = Owners.objects.all()
    species = Species.objects.all()

    if request.method == "POST":
        age_year = int(request.POST.get('age_year') or 0)
        age_month = int(request.POST.get('age_month') or 0)
        birth_date = date.today() - relativedelta(years=age_year, months=age_month)

        owner_id = request.POST.get('owner')
        species_id = request.POST.get('species')
        species_other = (request.POST.get('species_other') or '').strip()

        if not owner_id or not species_id:
            error = "Owner and species are required."
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'edit_pet.html', {
                'pet': pet,
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'age_year': age_year,
                'age_month': age_month,
                'error': error
            })

        if species_id == 'SP999':
            if not species_other:
                error = "กรุณาระบุชนิดสัตว์สำหรับ 'อื่นๆ'."
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'edit_pet.html', {
                    'pet': pet,
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'age_year': age_year,
                    'age_month': age_month,
                    'error': error
                })
            species_obj = Species.objects.filter(species_name__iexact=species_other).first()
            if not species_obj:
                new_species_id = get_next_id(Species, 'species_id', 'SP')
                species_obj = Species.objects.create(
                    species_id=new_species_id,
                    species_name=species_other,
                    description='Added from pet form'
                )
        else:
            try:
                species_obj = Species.objects.get(species_id=species_id)
            except Species.DoesNotExist:
                error = "Selected species does not exist."
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'edit_pet.html', {
                    'pet': pet,
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'age_year': age_year,
                    'age_month': age_month,
                    'error': error
                })

        try:
            owner = Owners.objects.get(owner_id=owner_id)
        except Owners.DoesNotExist:
            error = "Selected owner does not exist."
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'edit_pet.html', {
                'pet': pet,
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'age_year': age_year,
                'age_month': age_month,
                'error': error
            })
            error = "Selected owner or species does not exist."
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'edit_pet.html', {
                'pet': pet,
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'age_year': age_year,
                'age_month': age_month,
                'error': error
            })

        raw_gender = (request.POST.get('gender') or '').strip().lower()
        gender = None
        if raw_gender.startswith('m'):
            gender = 'M'
        elif raw_gender.startswith('f'):
            gender = 'F'

        weight_str = (request.POST.get('weight') or '').strip()
        weight = None
        if weight_str:
            try:
                weight = Decimal(weight_str)
            except (InvalidOperation, ValueError):
                error = "น้ำหนักต้องเป็นตัวเลข"
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'edit_pet.html', {
                    'pet': pet,
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'age_year': age_year,
                    'age_month': age_month,
                    'error': error
                })

            if weight <= 0:
                error = "น้ำหนักต้องมากกว่า 0"
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'edit_pet.html', {
                    'pet': pet,
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'age_year': age_year,
                    'age_month': age_month,
                    'error': error
                })

            if weight > Decimal('999.99'):
                error = "น้ำหนักต้องไม่เกิน 999.99 กิโลกรัม (จำกัดตาม schema)"
                years = list(range(0, 25))
                months = list(range(0, 12))
                return render(request, 'edit_pet.html', {
                    'pet': pet,
                    'owners': owners,
                    'species': species,
                    'years': years,
                    'months': months,
                    'age_year': age_year,
                    'age_month': age_month,
                    'error': error
                })

        pet.owner = owner
        pet.species = species_obj
        pet.pet_name = request.POST.get('pet_name')
        pet.breed = request.POST.get('breed')
        pet.gender = gender
        pet.birth_date = birth_date
        pet.weight = weight
        try:
            pet.save()
        except (IntegrityError, InvalidOperation):
            error = "ไม่สามารถบันทึกน้ำหนัก พยายามใช้ค่า 0-1000"
            years = list(range(0, 25))
            months = list(range(0, 12))
            return render(request, 'edit_pet.html', {
                'pet': pet,
                'owners': owners,
                'species': species,
                'years': years,
                'months': months,
                'age_year': age_year,
                'age_month': age_month,
                'error': error
            })

        if 'pet_image' in request.FILES:
            save_pet_image(pet.pet_id, request.FILES['pet_image'])
        return redirect('pet_list')

    years = list(range(0, 25))
    months = list(range(0, 12))
    age_year = 0
    age_month = 0
    if pet.birth_date:
        diff = relativedelta(date.today(), pet.birth_date)
        age_year = diff.years
        age_month = diff.months
    return render(request, 'edit_pet.html', {
        'pet': pet,
        'owners': owners,
        'species': species,
        'years': years,
        'months': months,
        'age_year': age_year,
        'age_month': age_month,
        'image_url': get_pet_image_url(pet.pet_id)
    })


@login_required
@forbid_user_role
def delete_pet(request, id):
    try:
        pet = get_object_or_404(Pets, pk=id)
        pet_name = pet.pet_name
        # Check if pet has appointments
        apt_count = Appointments.objects.filter(pet_id=id).count()
        if apt_count > 0:
            return render(request, 'error_delete.html', {
                'reason': f'สัตว์เลี้ยง "{pet_name}" มีการนัดหมายที่บันทึกไว้',
                'details': f'สัตว์เลี้ยงนี้มี {apt_count} รายการนัดหมาย โปรดลบข้อมูลนัดหมายก่อน'
            })
        # Check if pet has medical records
        record_count = MedicalRecords.objects.filter(pet_id=id).count()
        if record_count > 0:
            return render(request, 'error_delete.html', {
                'reason': f'สัตว์เลี้ยง "{pet_name}" มีประวัติการรักษาที่บันทึกไว้',
                'details': f'สัตว์เลี้ยงนี้มี {record_count} รายการประวัติการรักษา โปรดลบประวัติการรักษาก่อน'
            })
        pet.delete()
        return redirect('pet_list')
    except IntegrityError:
        return render(request, 'error_delete.html', {
            'reason': 'ไม่สามารถลบสัตว์เลี้ยงได้ เนื่องมีข้อมูลที่เกี่ยวข้องในระบบ',
            'details': 'โปรดตรวจสอบและลบข้อมูลที่เกี่ยวข้องก่อน'
        })


# APPOINTMENT
@login_required
def appointment_list(request):
    q = request.GET.get('q')
    owner_q = request.GET.get('owner')
    status_q = request.GET.get('status')
    date_q = request.GET.get('date')
    
    appointments = Appointments.objects.select_related('pet', 'pet__owner', 'vet', 'status')
    
    if q:
        appointments = appointments.filter(
            Q(appointment_id__icontains=q) |
            Q(pet__pet_name__icontains=q) |
            Q(vet__vet_name__icontains=q) |
            Q(reason__icontains=q)
        )
    
    if owner_q:
        appointments = appointments.filter(
            Q(pet__owner__first_name__icontains=owner_q) |
            Q(pet__owner__last_name__icontains=owner_q)
        )
    
    if status_q:
        appointments = appointments.filter(status__status_name=status_q)
    
    if date_q:
        appointments = appointments.filter(appointment_date=date_q)
    
    all_statuses = AppointmentStatus.objects.all()
    
    return render(request, 'appointments.html', {
        'appointments': appointments,
        'q': q,
        'owner': owner_q,
        'status': status_q,
        'date': date_q,
        'all_statuses': all_statuses
    })


@login_required
def add_appointment(request):
    if request.method == "POST":
        Appointments.objects.create(
            appointment_id=get_next_id(Appointments, 'appointment_id', 'APT'),
            pet_id=request.POST.get('pet'),
            vet_id=request.POST.get('veterinarian'),
            status_id=request.POST.get('status'),
            appointment_date=request.POST.get('appointment_date'),
            appointment_time=request.POST.get('appointment_time'),
            reason=request.POST.get('reason')
        )
        return redirect('appointment_list')

    return render(request, 'add_appointment.html', {
        'pet': Pets.objects.all(),
        'vets': Veterinarians.objects.all(),
        'statuses': AppointmentStatus.objects.all()
    })


@login_required
def edit_appointment(request, id):
    appointment = get_object_or_404(Appointments, pk=id)

    if request.method == "POST":
        appointment.pet_id = request.POST.get('pet')
        appointment.vet_id = request.POST.get('veterinarian')
        appointment.status_id = request.POST.get('status')
        appointment.appointment_date = request.POST.get('appointment_date')
        appointment.appointment_time = request.POST.get('appointment_time')
        appointment.reason = request.POST.get('reason')
        appointment.save()
        return redirect('appointment_list')

    return render(request, 'edit_appointment.html', {
        'appointment': appointment,
        'pet': Pets.objects.all(),
        'vets': Veterinarians.objects.all(),
        'statuses': AppointmentStatus.objects.all()
    })


@login_required
@forbid_user_role
def delete_appointment(request, id):
    try:
        appointment = get_object_or_404(Appointments, pk=id)
        apt_id = appointment.appointment_id
        appointment.delete()
        return redirect('appointment_list')
    except IntegrityError:
        return render(request, 'error_delete.html', {
            'reason': 'ไม่สามารถลบนัดหมายได้ เนื่องมีข้อมูลที่เกี่ยวข้องในระบบ',
            'details': 'โปรดตรวจสอบและลบข้อมูลที่เกี่ยวข้องก่อน'
        })


@login_required
def update_appointment_status(request, id):
    """AJAX endpoint to update appointment status"""
    if request.method == 'POST':
        try:
            appointment = get_object_or_404(Appointments, pk=id)
            status_name = request.POST.get('status')
            
            # Get the status object
            status_obj = AppointmentStatus.objects.filter(status_name=status_name).first()
            if not status_obj:
                return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
            
            appointment.status = status_obj
            appointment.save()
            
            # Return updated appointment data
            return JsonResponse({
                'success': True,
                'status': status_obj.status_name,
                'appointment_id': appointment.appointment_id,
                'message': f'Updated status to {status_obj.status_name}'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)


@csrf_exempt
@login_required
def get_appointment_detail(request, id):
    """AJAX endpoint to get appointment details for modal"""
    try:
        appointment = get_object_or_404(Appointments, pk=id)
        
        # Extract data safely, allowing for missing relationships and fields
        try:
            # Pet info
            pet_name = 'ไม่ระบุ'
            if appointment.pet:
                pet_name = getattr(appointment.pet, 'pet_name', None) or 'ไม่ระบุ'
            
            # Owner info
            owner_name = 'ไม่ระบุ'
            phone = ''
            if appointment.pet and appointment.pet.owner:
                first_name = getattr(appointment.pet.owner, 'first_name', '') or ''
                last_name = getattr(appointment.pet.owner, 'last_name', '') or ''
                owner_name = f"{first_name} {last_name}".strip() or 'ไม่ระบุ'
                phone = getattr(appointment.pet.owner, 'phone_number', '') or ''
            
            # Date and time
            date_str = '-'
            if hasattr(appointment, 'appointment_date') and appointment.appointment_date:
                try:
                    date_str = appointment.appointment_date.strftime('%d/%m/%Y')
                except:
                    date_str = str(appointment.appointment_date)
            
            time_str = '-'
            if hasattr(appointment, 'appointment_time') and appointment.appointment_time:
                try:
                    time_str = appointment.appointment_time.strftime('%H:%M')
                except:
                    time_str = str(appointment.appointment_time)
            
            # Vet info
            vet_name = 'ไม่มี'
            if appointment.vet:
                vet_name = getattr(appointment.vet, 'vet_name', None) or 'ไม่มี'
            
            # Other info
            reason = getattr(appointment, 'reason', None) or 'ไม่มี'
            status_name = 'Unknown'
            if appointment.status:
                status_name = getattr(appointment.status, 'status_name', None) or 'Unknown'
            
            note = getattr(appointment, 'note', '') or ''
            
        except Exception as field_error:
            # If there's an error extracting fields, return partial data
            return JsonResponse({
                'success': True,
                'appointment': {
                    'appointment_id': str(appointment.appointment_id),
                    'pet_name': 'ข้อมูลไม่สมบูรณ์',
                    'owner_name': 'ข้อมูลไม่สมบูรณ์',
                    'date': '-',
                    'time': '-',
                    'vet_name': 'ไม่มี',
                    'reason': 'ไม่มี',
                    'status': 'Unknown',
                    'phone': '',
                    'note': ''
                }
            })
        
        data = {
            'appointment_id': str(appointment.appointment_id),
            'pet_name': pet_name,
            'owner_name': owner_name,
            'date': date_str,
            'time': time_str,
            'vet_name': vet_name,
            'reason': reason,
            'status': status_name,
            'phone': phone,
            'note': note
        }
        
        return JsonResponse({'success': True, 'appointment': data})
        
    except Appointments.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'ไม่พบนัดหมายที่มีรหัส: {id}'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': True,
            'appointment': {
                'appointment_id': str(id),
                'pet_name': 'ข้อมูลไม่สมบูรณ์',
                'owner_name': 'ข้อมูลไม่สมบูรณ์',
                'date': '-',
                'time': '-',
                'vet_name': 'ไม่มี',
                'reason': 'ไม่มี',
                'status': 'Unknown',
                'phone': '',
                'note': ''
            }
        })


# MEDICAL
@login_required
def medical_records(request):
    q = request.GET.get('q')
    pet_id = request.GET.get('pet')
    records = MedicalRecords.objects.select_related('pet', 'vet')
    if pet_id:
        records = records.filter(pet_id=pet_id)
    if q:
        records = records.filter(
            Q(record_id__icontains=q) |
            Q(pet__pet_name__icontains=q) |
            Q(vet__vet_name__icontains=q) |
            Q(symptoms__icontains=q) |
            Q(diagnosis__icontains=q) |
            Q(treatment__icontains=q)
        )
    bills = {b.record_id: b for b in Bills.objects.select_related('record').all()}
    
    # เก็บ record_id ของบิลที่ชำระแล้วเท่านั้น
    paid_bills = set(Bills.objects.filter(payment_method__isnull=False).values_list('record_id', flat=True))
    
    return render(request, 'medical_records.html', {
        'records': records,
        'bills': bills,
        'paid_bills': paid_bills,
        'q': q,
        'pet_id': pet_id,
        'treatments': Treatments.objects.select_related('medicine').all()
    })


@login_required
def add_medical_record(request):
    error = None
    if request.method == "POST":
        pet_id = request.POST.get('pet')
        vet_id = request.POST.get('veterinarian')
        symptoms = request.POST.get('symptoms')
        diagnosis = request.POST.get('diagnosis')
        treatment_text = request.POST.get('treatment')
        
        # Parse medicines_data JSON from frontend
        import json
        medicines_data = request.POST.get('medicines_data', '[]')
        try:
            medicines_list = json.loads(medicines_data)
        except (json.JSONDecodeError, ValueError):
            medicines_list = []

        valid_items = []
        for med_data in medicines_list:
            med_id = med_data.get('id')
            qty_str = med_data.get('quantity')
            if not med_id:
                continue
            try:
                qty = int(qty_str or 0)
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                valid_items.append((med_id, qty))

        if not pet_id or not diagnosis or not valid_items:
            error = 'Please fill pet, diagnosis, and at least one medicine/quantity.'
        else:
            record = MedicalRecords.objects.create(
                record_id=get_next_id(MedicalRecords, 'record_id', 'MR'),
                pet_id=pet_id,
                vet_id=vet_id,
                visit_date=request.POST.get('visit_date') or date.today(),
                symptoms=symptoms,
                diagnosis=diagnosis,
                treatment=treatment_text
            )

            total = 0
            for med_id, qty in valid_items:
                med = Medicines.objects.get(pk=med_id)
                stock = MedicineStock.objects.filter(medicine_id=med_id).first()
                if not stock or stock.quantity is None or stock.quantity < qty:
                    record.delete()
                    error = f'Insufficient stock for {med.medicine_name}. Available: {stock.quantity if stock else 0}.'
                    break

                Treatments.objects.create(
                    treatment_id=str(uuid.uuid4())[:6],
                    record=record,
                    medicine=med,
                    quantity=qty
                )
                # deduct stock
                stock.quantity = stock.quantity - qty
                stock.save()
                MedicineStockTransaction.objects.create(
                    medicine_id=med_id,
                    quantity_change=-qty,
                    note=f"การรักษา {record.record_id}"
                )
                total += (med.price or 0) * qty

            if not error:
                Bills.objects.create(
                    bill_id=get_next_id(Bills, 'bill_id', 'B', width=5),
                    record=record,
                    total_amount=total,
                    bill_date=date.today()
                )
                return redirect('medical_records')

    medicines = list(Medicines.objects.all())
    stock_by_med = {
        s.medicine_id: (s.quantity or 0)
        for s in MedicineStock.objects.filter(medicine_id__in=[m.medicine_id for m in medicines])
    }
    for m in medicines:
        m.current_stock = stock_by_med.get(m.medicine_id, 0)
    
    medicines = [m for m in medicines if m.current_stock > 0]

    total_stock = MedicineStock.objects.aggregate(total=Sum('quantity'))['total'] or 0

    return render(request, 'add_medical_record.html', {
        'pet': Pets.objects.all(),
        'vets': Veterinarians.objects.all(),
        'medicines': medicines,
        'total_stock': total_stock,
        'error': error
    })


@login_required
def edit_medical_record(request, id):
    record = get_object_or_404(MedicalRecords, pk=id)
    error = None
    
    # ตรวจสอบว่าบิลของประวัติการรักษานี้ถูกจ่ายไปแล้วหรือไม่
    bill = Bills.objects.filter(record=record).first()
    bill_is_paid = bill and bill.paid_amount and Decimal(str(bill.paid_amount)) > 0
    
    if bill_is_paid and request.method == "POST":
        # ถ้าบิลถูกจ่ายไปแล้วไม่อนุญาตให้แก้ไข
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่สามารถแก้ไขได้',
            'error_message': 'ประวัติการรักษานี้ได้ชำระเงินแล้ว',
            'error_reason': 'เพื่อป้องกันความผิดพลาดทางการเงิน ระบบไม่อนุญาตให้แก้ไขประวัติการรักษาที่ได้ชำระเงินแล้ว'
        })

    if request.method == "POST":
        record.pet_id = request.POST.get('pet')
        record.vet_id = request.POST.get('veterinarian')
        record.visit_date = request.POST.get('visit_date') or record.visit_date or date.today()
        record.symptoms = request.POST.get('symptoms')
        record.diagnosis = request.POST.get('diagnosis')
        record.treatment = request.POST.get('treatment')
        record.save()

        # Parse medicines_data JSON from frontend
        import json
        medicines_data = request.POST.get('medicines_data', '[]')
        try:
            medicines_list = json.loads(medicines_data)
        except (json.JSONDecodeError, ValueError):
            medicines_list = []

        # Add new medicines from the form
        for med_data in medicines_list:
            med_id = med_data.get('id')
            qty_str = med_data.get('quantity')
            if not med_id:
                continue
            try:
                qty = int(qty_str or 0)
            except (ValueError, TypeError):
                qty = 0
            
            if qty > 0:
                med = Medicines.objects.get(pk=med_id)
                stock = MedicineStock.objects.filter(medicine_id=med_id).first()
                if not stock or stock.quantity is None or stock.quantity < qty:
                    error = f'Insufficient stock for {med.medicine_name}. Available: {stock.quantity if stock else 0}.'
                    break
                else:
                    Treatments.objects.create(
                        treatment_id=str(uuid.uuid4())[:6],
                        record=record,
                        medicine=med,
                        quantity=qty
                    )
                    stock.quantity -= qty
                    stock.save()
                    MedicineStockTransaction.objects.create(
                        medicine_id=med_id,
                        quantity_change=-qty,
                        note=f"การรักษาอัปเดท {record.record_id}"
                    )

        # recalc bill total
        treatments = Treatments.objects.filter(record=record).select_related('medicine')
        pre_vat = sum((t.quantity or 0) * (t.medicine.price or 0) for t in treatments)
        vat = pre_vat * Decimal('0.07')
        total_with_vat = pre_vat + vat
        bill = Bills.objects.filter(record=record).first()
        if bill:
            bill.total_amount = total_with_vat
            bill.save()
        else:
            bill = Bills.objects.create(
                bill_id=get_next_id(Bills, 'bill_id', 'B', width=5),
                record=record,
                total_amount=total_with_vat,
                bill_date=date.today()
            )

        if not error:
            return redirect('medical_records')

    bill = Bills.objects.filter(record=record).first()
    treatments = Treatments.objects.filter(record=record).select_related('medicine')

    medicines = list(Medicines.objects.all())
    stock_by_med = {
        s.medicine_id: (s.quantity or 0)
        for s in MedicineStock.objects.filter(medicine_id__in=[m.medicine_id for m in medicines])
    }
    for m in medicines:
        m.current_stock = stock_by_med.get(m.medicine_id, 0)
    
    medicines = [m for m in medicines if m.current_stock > 0]

    total_stock = MedicineStock.objects.aggregate(total=Sum('quantity'))['total'] or 0

    return render(request, 'edit_medical_record.html', {
        'record': record,
        'pet': Pets.objects.all(),
        'vets': Veterinarians.objects.all(),
        'medicines': medicines,
        'total_stock': total_stock,
        'bill': bill,
        'bill_is_paid': bill_is_paid,
        'treatments': treatments,
        'error': error
    })


@login_required
def remove_treatment(request, id, treatment_id):
    record = get_object_or_404(MedicalRecords, pk=id)
    
    # ตรวจสอบว่าบิลถูกจ่ายแล้วหรือไม่
    bill = Bills.objects.filter(record=record).first()
    bill_is_paid = bill and bill.paid_amount and Decimal(str(bill.paid_amount)) > 0
    
    if bill_is_paid:
        # ถ้าบิลถูกจ่ายแล้วไม่อนุญาตให้ลบ treatment
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่สามารถลบได้',
            'error_message': 'ประวัติการรักษานี้ได้ชำระเงินแล้ว',
            'error_reason': 'เพื่อป้องกันความผิดพลาดทางการเงิน ระบบไม่อนุญาตให้ลบยาจากประวัติการรักษาที่ได้ชำระเงินแล้ว'
        })
    
    treatment = get_object_or_404(Treatments, pk=treatment_id, record=record)
    stock = MedicineStock.objects.filter(medicine_id=treatment.medicine_id).first()
    if stock:
        stock.quantity = (stock.quantity or 0) + (treatment.quantity or 0)
        stock.save()
        MedicineStockTransaction.objects.create(
            medicine_id=treatment.medicine_id,
            quantity_change=treatment.quantity,
            note=f"ยกเลิกการรักษา {record.record_id}"
        )
    treatment.delete()

    treatments = Treatments.objects.filter(record=record).select_related('medicine')
    total = sum((t.quantity or 0) * (t.medicine.price or 0) for t in treatments)
    bill = Bills.objects.filter(record=record).first()
    if bill:
        bill.total_amount = total
        bill.save()
    return redirect('edit_medical_record', id=record.record_id)


@login_required
@forbid_user_role
def delete_medical_record(request, id):
    record = get_object_or_404(MedicalRecords, pk=id)
    
    # ตรวจสอบว่าบิลถูกจ่ายแล้วหรือไม่
    bill = Bills.objects.filter(record=record).first()
    bill_is_paid = bill and bill.paid_amount and Decimal(str(bill.paid_amount)) > 0
    
    if bill_is_paid:
        # ถ้าบิลถูกจ่ายแล้วไม่อนุญาตให้ลบ
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่สามารถลบได้',
            'error_message': 'ประวัติการรักษานี้ได้ชำระเงินแล้ว',
            'error_reason': 'เพื่อป้องกันความผิดพลาดทางการเงิน ระบบไม่อนุญาตให้ลบประวัติการรักษาที่ได้ชำระเงินแล้ว'
        })

    # คืนสต็อกจากทรีตเมนต์และ log transaction
    treatments = Treatments.objects.filter(record=record).select_related('medicine')
    for t in treatments:
        stock = MedicineStock.objects.filter(medicine_id=t.medicine_id).first()
        if stock:
            stock.quantity = (stock.quantity or 0) + (t.quantity or 0)
            stock.save()
        MedicineStockTransaction.objects.create(
            medicine_id=t.medicine_id,
            quantity_change=(t.quantity or 0),
            note=f"ยกเลิกการบันทึก {record.record_id}"
        )

    # ลบ Bills ก่อน
    Bills.objects.filter(record=record).delete()

    # ลบ Treatments ก่อน
    treatments.delete()

    # แล้วค่อยลบ record
    record.delete()

    return redirect('medical_records')


@login_required
def pos(request):
    # POS cart state in session
    cart = request.session.get('pos_cart', [])
    selected_customer_id = request.session.get('pos_customer_id')
    message = ''
    error = ''

    owners = Owners.objects.all()
    medicines = list(Medicines.objects.select_related('supplier').filter(type__in=['อาหารสัตว์', 'อาหารเสริม', 'ผลิตภัณฑ์ดูแลสัตว์', 'อุปกรณ์สัตว์เลี้ยง']))
    stock_by_med = {
        s.medicine_id: (s.quantity or 0)
        for s in MedicineStock.objects.filter(medicine_id__in=[m.medicine_id for m in medicines])
    }
    for m in medicines:
        m.current_stock = stock_by_med.get(m.medicine_id, 0)
    
    medicines = [m for m in medicines if m.current_stock > 0]

    if request.method == 'POST':
        action = request.POST.get('action')

        # Add an item to cart
        if action == 'add_item':
            selected_customer_id = request.POST.get('customer') or selected_customer_id
            medicine_id = request.POST.get('medicine')
            qty = int(request.POST.get('quantity') or 0)

            if not selected_customer_id:
                error = 'กรุณาเลือกลูกค้าก่อนเพิ่มรายการ'
            elif not medicine_id or qty <= 0:
                error = 'กรุณาเลือกสินค้าและจำนวนอย่างน้อย 1'
            else:
                try:
                    med = Medicines.objects.get(pk=medicine_id)
                    stock = MedicineStock.objects.filter(medicine_id=medicine_id).first()
                    if not stock or (stock.quantity or 0) < qty:
                        error = f'สต็อกไม่พอสำหรับ {med.medicine_name} (คงเหลือ {stock.quantity if stock else 0})'
                    else:
                        # add or update cart
                        item = next((i for i in cart if i['medicine_id'] == medicine_id), None)
                        if item:
                            item['quantity'] += qty
                            item['subtotal'] = float(item['quantity']) * float(med.price or 0)
                        else:
                            cart.append({
                                'medicine_id': medicine_id,
                                'medicine_name': med.medicine_name,
                                'unit_price': float(med.price or 0),
                                'quantity': qty,
                                'subtotal': float(qty) * float(med.price or 0)
                            })
                        request.session['pos_cart'] = cart
                        request.session['pos_customer_id'] = selected_customer_id
                        message = f'เพิ่ม {med.medicine_name} ({qty}) เรียบร้อยแล้ว'
                except Medicines.DoesNotExist:
                    error = 'ไม่พบรายการสินค้า'

        # Remove line item
        elif action == 'remove_item':
            item_id = request.POST.get('medicine_id')
            cart = [i for i in cart if i['medicine_id'] != item_id]
            request.session['pos_cart'] = cart
            message = 'ลบรายการสินค้าเรียบร้อยแล้ว'

        # Checkout and create POS transactions
        elif action == 'checkout':
            selected_customer_id = request.POST.get('customer') or selected_customer_id
            if not selected_customer_id:
                error = 'กรุณาเลือกลูกค้าก่อนชำระเงิน'
            elif not cart:
                error = 'ไม่มีรายการสินค้าในรถเข็น'
            else:
                try:
                    customer_id = selected_customer_id
                    total_amount = 0
                    
                    # Generate bill number from both Bills + POSBills (จะไม่ซ้ำอีก)
                    bill_id = get_next_bill_id('B')

                    total_amount = 0
                    for item in cart:
                        med = Medicines.objects.get(pk=item['medicine_id'])
                        qty = int(item['quantity'])
                        unit_price = float(item['unit_price'])
                        subtotal = unit_price * qty

                        if qty <= 0:
                            continue

                        # stock check
                        stock = MedicineStock.objects.filter(medicine_id=med.medicine_id).first()
                        if not stock or (stock.quantity or 0) < qty:
                            error = f'สต็อกไม่พอสำหรับ {med.medicine_name} (คงเหลือ {stock.quantity if stock else 0})'
                            break

                        # Create POS transaction with bill_id
                        POSTransaction.objects.create(
                            bill_id=bill_id,
                            customer_id=customer_id,
                            medicine_id=med.medicine_id,
                            quantity=qty,
                            unit_price=unit_price,
                            total_amount=subtotal
                        )

                        # Update stock
                        stock.quantity = (stock.quantity or 0) - qty
                        stock.save()
                        
                        # Create stock transaction record
                        MedicineStockTransaction.objects.create(
                            medicine_id=med.medicine_id,
                            quantity_change=-qty,
                            note=f'การขายผ่าน POS ไปยังลูกค้า {customer_id} (บิล {bill_id})'
                        )

                        total_amount += subtotal

                    if not error:
                        pre_vat = round(total_amount, 2)
                        vat_amount = round(pre_vat * 0.07, 2)
                        total_with_vat = round(pre_vat + vat_amount, 2)

                        request.session['pos_cart'] = []
                        request.session['pos_customer_id'] = None
                        message = f'บันทึกการขายสำเร็จ บิล {bill_id} ยอดรวมก่อน VAT {pre_vat:.2f} VAT {vat_amount:.2f} รวม {total_with_vat:.2f} บาท'
                        
                        # redirect to receipt page immediately
                        return redirect('pos_receipt', bill_id=bill_id)

                except Owners.DoesNotExist:
                    error = 'ลูกค้าที่เลือกไม่มีอยู่'

    # Update virtual stock in POS page (cart-level) so user sees remaining stock before checkout
    cart_qty_by_med = {}
    for item in cart:
        cart_qty_by_med[item['medicine_id']] = cart_qty_by_med.get(item['medicine_id'], 0) + int(item.get('quantity', 0))

    for m in medicines:
        current = getattr(m, 'current_stock', 0) or 0
        m.current_stock = max(0, current - cart_qty_by_med.get(m.medicine_id, 0))

    total = round(sum(i['subtotal'] for i in cart), 2)

    # Get POS receipts grouped by bill_id
    pos_transactions = POSTransaction.objects.select_related('customer').order_by('-transaction_date')
    
    # Group transactions by bill_id and get summary
    from collections import defaultdict
    bill_groups = defaultdict(lambda: {'bill_id': None, 'customer_name': '', 'item_count': 0, 'total_amount': 0.0})
    
    for tx in pos_transactions:
        bill_id = tx.bill_id
        if bill_id not in bill_groups:
            customer = tx.customer
            customer_name = f'{customer.first_name} {customer.last_name}' if customer else 'ไม่ทราบ'
            bill_groups[bill_id] = {
                'bill_id': bill_id,
                'customer_name': customer_name,
                'item_count': 0,
                'total_amount': 0.0
            }
        bill_groups[bill_id]['item_count'] += tx.quantity
        bill_groups[bill_id]['total_amount'] += float(tx.total_amount or 0)
    
    pos_receipts = list(bill_groups.values())[:10]  # Get latest 10 bills
    latest_receipt = pos_receipts[0] if pos_receipts else None

    current_total_stock = MedicineStock.objects.aggregate(total=Sum('quantity'))['total'] or 0

    return render(request, 'pos.html', {
        'owners': owners,
        'medicines': medicines,
        'cart': cart,
        'selected_customer_id': selected_customer_id,
        'total': total,
        'message': message,
        'error': error,
        'pos_receipts': pos_receipts,
        'latest_receipt': latest_receipt,
        'total_stock': current_total_stock,
    })


@login_required
def bill_detail(request, id):
    bill = get_object_or_404(Bills, pk=id)
    record = bill.record
    pet = record.pet
    owner = pet.owner
    treatments_qs = Treatments.objects.filter(record=record).select_related('medicine')
    treatments = []
    total_items = 0
    for t in treatments_qs:
        subtotal = (t.quantity or 0) * (t.medicine.price or 0)
        treatments.append({
            'medicine': t.medicine,
            'quantity': t.quantity,
            'unit_price': t.medicine.price,
            'subtotal': subtotal
        })
        total_items += (t.quantity or 0)
    
    # Recalculate total from treatments
    pre_vat_calc = sum((Decimal(t.quantity or 0) * (t.medicine.price or Decimal('0.00'))) for t in treatments_qs)
    vat_calc = (pre_vat_calc * Decimal('0.07')).quantize(Decimal('0.01'))
    total_calc = (pre_vat_calc + vat_calc).quantize(Decimal('0.01'))
    
    if abs(Decimal(bill.total_amount or 0) - total_calc) > Decimal('0.01'):  # if different, update
        bill.total_amount = total_calc
        bill.save()
    
    total = total_calc
    pre_vat = pre_vat_calc
    vat = vat_calc
    
    return render(request, 'bill_detail.html', {
        'bill': bill,
        'pet': pet,
        'owner': owner,
        'treatments': treatments,
        'total': total,
        'pre_vat': pre_vat,
        'vat': vat,
        'total_items': total_items
    })


@login_required
def pay_bill(request, id):
    bill = get_object_or_404(Bills, pk=id)
    method_names = ['เงินสด', 'QR code']
    error = None
    
    # Recalculate total from treatments to ensure bill.total_amount is correct
    record = bill.record
    treatments_qs = Treatments.objects.filter(record=record).select_related('medicine')
    pre_vat_calc = sum((Decimal(t.quantity or 0) * (t.medicine.price or Decimal('0.00'))) for t in treatments_qs)
    vat_calc = (pre_vat_calc * Decimal('0.07')).quantize(Decimal('0.01'))
    total_calc = (pre_vat_calc + vat_calc).quantize(Decimal('0.01'))
    
    if abs(Decimal(bill.total_amount or 0) - total_calc) > Decimal('0.01'):  # if different, update
        bill.total_amount = total_calc
        bill.save()
    
    total = total_calc
    pre_vat = pre_vat_calc
    vat = vat_calc

    if request.method == 'POST':
        method_name = request.POST.get('payment_method')
        paid_amount = request.POST.get('paid_amount')
        bill_date = request.POST.get('payment_date')

        if not method_name:
            error = 'กรุณาเลือกวิธีการชำระเงิน'
        elif method_name not in method_names:
            error = 'วิธีการชำระเงินไม่ถูกต้อง'
        elif not paid_amount:
            error = 'กรุณากรอกจำนวนเงินที่ชำระ'
        else:
            try:
                paid_amount_decimal = Decimal(str(paid_amount))
                if paid_amount_decimal < total:
                    error = f'จำนวนเงินที่ชำระต้องไม่น้อยกว่ายอดบิล ({total:.2f} บาท)'
                else:
                    # Validation passed - get or create payment method
                    method, _ = PaymentMethod.objects.get_or_create(
                        method_name=method_name,
                        defaults={'payment_method_id': get_next_id(PaymentMethod, 'payment_method_id', 'PM')}
                    )
            except (ValueError, InvalidOperation):
                error = 'จำนวนเงินไม่ถูกต้อง กรุณากรอกตัวเลข'

        qr_image = request.POST.get('qr_image', '').strip()
        if not error:
            bill.payment_method = method
            bill.paid_amount = paid_amount_decimal
            bill.bill_date = bill_date or bill.bill_date or date.today()
            bill.save()
            return redirect('paid_bill', id=bill.bill_id)

    else:
        qr_image = ''

    return render(request, 'pay_bill.html', {
        'bill': bill,
        'method_names': method_names,
        'error': error,
        'qr_image': qr_image,
        'pre_vat': pre_vat,
        'vat': vat
    })


@login_required
def paid_bill(request, id):
    bill = get_object_or_404(Bills, pk=id)
    if not bill.payment_method:
        return redirect('bill_detail', id=bill.bill_id)

    record = bill.record
    pet = record.pet
    owner = pet.owner
    treatment_qs = Treatments.objects.filter(record=record).select_related('medicine')
    treatments = []
    total_items = 0
    for t in treatment_qs:
        subtotal = (Decimal(t.quantity or 0) * (t.medicine.price or Decimal('0.00')))
        treatments.append({'medicine': t.medicine, 'quantity': t.quantity, 'unit_price': t.medicine.price, 'subtotal': subtotal})
        total_items += (t.quantity or 0)

    # Recalculate total from treatments
    pre_vat_calc = sum((Decimal(t.quantity or 0) * (t.medicine.price or Decimal('0.00'))) for t in treatment_qs)
    vat_calc = (pre_vat_calc * Decimal('0.07')).quantize(Decimal('0.01'))
    total_calc = (pre_vat_calc + vat_calc).quantize(Decimal('0.01'))
    
    if abs(Decimal(bill.total_amount or 0) - total_calc) > Decimal('0.01'):  # if different, update
        bill.total_amount = total_calc
        bill.save()

    change = Decimal('0.00')
    if bill.paid_amount and bill.paid_amount > total_calc:
        change = (bill.paid_amount - total_calc).quantize(Decimal('0.01'))

    return render(request, 'paid_bill.html', {
        'bill': bill,
        'pet': pet,
        'owner': owner,
        'treatments': treatments,
        'total_items': total_items,
        'pre_vat': pre_vat_calc,
        'vat': vat_calc,
        'total': total_calc,
        'paid_amount': bill.paid_amount,
        'change': change
    })


@login_required
def paid_bills(request):
    bills = Bills.objects.filter(payment_method__isnull=False).select_related('record__pet__owner', 'payment_method')
    return render(request, 'paid_bills.html', {
        'bills': bills
    })


@login_required
def unpaid_bills(request):
    bills = Bills.objects.filter(payment_method__isnull=True).select_related('record__pet__owner')
    return render(request, 'unpaid_bills.html', {
        'bills': bills
    })



# MEDICINE
@login_required
def medicines(request):
    q = request.GET.get('q')
    type_filter = request.GET.get('type_filter')
    med_data = Medicines.objects.select_related('supplier')
    if q:
        med_data = med_data.filter(
            Q(medicine_id__icontains=q) |
            Q(medicine_name__icontains=q) |
            Q(type__icontains=q) |
            Q(supplier__supplier_name__icontains=q)
        )
    if type_filter:
        med_data = med_data.filter(type=type_filter)
    med_data = med_data.all()
    stock = MedicineStock.objects.select_related('medicine')
    stock_by_med = {s.medicine_id: s for s in stock}
    medicines = []
    for m in med_data:
        s = stock_by_med.get(m.medicine_id)
        quantity = s.quantity if s else 0
        medicines.append({
            'medicine': m,
            'stock': quantity,
            'is_low': quantity < 10
        })

    total_stock = sum(item['stock'] for item in medicines)

    return render(request, 'medicines.html', {
        'medicines': medicines,
        'q': q,
        'type_filter': type_filter,
        'type_choices': Medicines.TYPE_CHOICES,
        'total_stock': total_stock
    })


@login_required
@forbid_user_role
def add_medicine(request):
    error = None
    if request.method == "POST":
        supplier_id = request.POST.get('supplier')
        if not supplier_id:
            error = 'Please select supplier.'
        else:
            medicine_id = get_next_id(Medicines, 'medicine_id', 'MED')
            med = Medicines.objects.create(
                medicine_id=medicine_id,
                supplier_id=supplier_id,
                medicine_name=request.POST.get('medicine_name'),
                type=request.POST.get('medicine_type'),
                price=request.POST.get('price')
            )
            stock_qty = int(request.POST.get('stock') or 0)
            if stock_qty > 0:
                MedicineStock.objects.create(
                    stock_id=str(uuid.uuid4())[:6],
                    medicine_id=medicine_id,
                    quantity=stock_qty
                )
                MedicineStockTransaction.objects.create(
                    medicine_id=medicine_id,
                    quantity_change=stock_qty,
                    note=f"สินค้าเริ่มต้น {medicine_id}"
                )
            return redirect('medicines')
    return render(request, 'add_medicine.html', {
        'error': error,
        'suppliers': Suppliers.objects.all()
    })


@login_required
@forbid_user_role
def edit_medicine(request, id):
    m = get_object_or_404(Medicines, pk=id)
    stock = MedicineStock.objects.filter(medicine_id=m.medicine_id).first()
    error = None
    if request.method == "POST":
        supplier_id = request.POST.get('supplier')
        if not supplier_id:
            error = 'Please select supplier.'
        else:
            m.supplier_id = supplier_id
            m.medicine_name = request.POST.get('medicine_name')
            m.type = request.POST.get('medicine_type')
            m.price = request.POST.get('price')
            m.save()
            stock_qty = int(request.POST.get('stock') or 0)
            if stock:
                old_qty = stock.quantity or 0
                stock.quantity = stock_qty
                stock.save()
                diff = stock_qty - old_qty
                if diff != 0:
                    MedicineStockTransaction.objects.create(
                        medicine_id=m.medicine_id,
                        quantity_change=diff,
                        note=f"ปรับสต็อก {m.medicine_id}"
                    )
            else:
                MedicineStock.objects.create(
                    stock_id=str(uuid.uuid4())[:6],
                    medicine_id=m.medicine_id,
                    quantity=stock_qty
                )
                if stock_qty != 0:
                    MedicineStockTransaction.objects.create(
                        medicine_id=m.medicine_id,
                        quantity_change=stock_qty,
                        note=f"สินค้าสร้างในการแก้ไข {m.medicine_id}"
                    )
            return redirect('medicines')
    return render(request, 'edit_medicine.html', {
        'medicine': m,
        'stock': stock,
        'suppliers': Suppliers.objects.all(),
        'error': error
    })


@login_required
@forbid_user_role
def delete_medicine(request, id):
    try:
        medicine = get_object_or_404(Medicines, pk=id)
        med_name = medicine.medicine_name
        # Check if medicine is used in treatments
        treatment_count = Treatments.objects.filter(medicine_id=id).count()
        if treatment_count > 0:
            return render(request, 'error_delete.html', {
                'reason': f'สินค้า "{med_name}" ถูกใช้ในการบันทึกประวัติการรักษา',
                'details': f'สินค้านี้ถูกใช้ใน {treatment_count} รายการประวัติการรักษา ไม่สามารถลบได้'
            })
        medicine.delete()
        return redirect('medicines')
    except IntegrityError:
        return render(request, 'error_delete.html', {
            'reason': 'ไม่สามารถลบสินค้าได้ เนื่องมีข้อมูลที่เกี่ยวข้องในระบบ',
            'details': 'โปรดตรวจสอบและลบข้อมูลที่เกี่ยวข้องก่อน'
        })


@login_required
def reports(request):
    return render(request, 'reports.html')


@login_required
def report_appointments(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    status = request.GET.get('status')
    qs = Appointments.objects.select_related('pet', 'status')
    if start_date:
        qs = qs.filter(appointment_date__gte=start_date)
    if end_date:
        qs = qs.filter(appointment_date__lte=end_date)
    if status and status != 'all':
        qs = qs.filter(status__status_name=status)

    total = qs.count()
    scheduled = qs.filter(status__status_name='Scheduled').count()
    completed = qs.filter(status__status_name='Completed').count()
    cancelled = qs.filter(status__status_name='Cancelled').count()
    return render(request, 'report_appointments.html', {
        'appointments': qs.order_by('-appointment_date', '-appointment_time'),
        'total': total,
        'scheduled': scheduled,
        'completed': completed,
        'cancelled': cancelled,
        'start_date': start_date,
        'end_date': end_date,
        'status': status or 'all'
    })


@login_required
def report_stock_status(request):
    # รับ filter จาก URL เช่น ?filter=low
    filter_type = request.GET.get('filter')

    med_data = Medicines.objects.select_related('supplier').all()
    stock_data = MedicineStock.objects.select_related('medicine')
    stock_by_med = {s.medicine_id: s for s in stock_data}

    rows = []
    for med in med_data:
        stock = stock_by_med.get(med.medicine_id)
        qty = stock.quantity if stock else 0
        status = 'Low' if qty < 10 else 'OK'

        # กรองเฉพาะ Low ถ้ามี filter
        if filter_type == 'low' and status != 'Low':
            continue

        rows.append({
            'medicine': med,
            'stock': qty,
            'status': status,
            'supplier': med.supplier
        })

    total_stock = sum(r['stock'] for r in rows)
    low_count = sum(1 for r in rows if r['status'] == 'Low')
    ok_count = sum(1 for r in rows if r['status'] != 'Low')

    return render(request, 'report_stock_status.html', {
        'rows': rows,
        'total_stock': total_stock,
        'low_count': low_count,
        'ok_count': ok_count
    })


from datetime import datetime, timedelta
from django.utils import timezone

@login_required
def report_stock_ledger(request):
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    medicine_id = request.GET.get('medicine')

    reconcile_stock_from_transactions()

    txns = MedicineStockTransaction.objects.all().order_by('transaction_date')

    # ✅ START DATE
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            start_date = timezone.make_aware(start_date)
            txns = txns.filter(transaction_date__gte=start_date)
        except (ValueError, TypeError):
            pass

    # ✅ END DATE
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date = end_date + timedelta(days=1)
            end_date = timezone.make_aware(end_date)
            txns = txns.filter(transaction_date__lt=end_date)
        except (ValueError, TypeError):
            pass

    if medicine_id:
        txns = txns.filter(medicine_id=medicine_id)

    medicines = Medicines.objects.all()

    ledger = []
    balance_by_med = {}
    total_inbound = 0
    total_outbound = 0
    medicine_names = {m.medicine_id: m.medicine_name for m in medicines}
    for t in txns.order_by('transaction_date'):
        mid = t.medicine_id
        balance_by_med[mid] = balance_by_med.get(mid, 0) + (t.quantity_change or 0)
        inbound = t.quantity_change if t.quantity_change > 0 else 0
        outbound = abs(t.quantity_change) if t.quantity_change < 0 else 0
        total_inbound += inbound
        total_outbound += outbound
        ledger.append({
            'date': t.transaction_date,
            'medicine': medicine_names.get(mid, mid),
            'inbound': inbound,
            'outbound': outbound,
            'balance': balance_by_med[mid],
            'note': t.note
        })

    current_balance_rows = []
    # Reconcile stock values before rendering
    reconcile_stock_from_transactions()
    for stock in MedicineStock.objects.select_related('medicine').all():
        current_balance_rows.append({
            'medicine': stock.medicine.medicine_name,
            'qty': stock.quantity or 0
        })

    current_total_stock = MedicineStock.objects.aggregate(total=Sum('quantity'))['total'] or 0

    return render(request, 'report_stock_ledger.html', {
        'ledger': ledger,
        'medicines': medicines,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'medicine_id': medicine_id,
        'current_balance_rows': current_balance_rows,
        'total_inbound': total_inbound,
        'total_outbound': total_outbound,
        'total_stock': current_total_stock,
    })


@login_required
def report_payments(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    bills = Bills.objects.filter(payment_method__isnull=False)
    
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    total = bills.aggregate(total_amount=Sum('total_amount'))['total_amount'] or 0

    return render(request, 'report_payments.html', {
        'bills': bills.select_related('record__pet__owner', 'payment_method').order_by('-bill_id'),
        'total_amount': total,
        'start_date': start_date,
        'end_date': end_date,
    })


@login_required
def report_animals(request):
    total_pets = Pets.objects.count()
    pets_by_species = Pets.objects.values('species__species_name').annotate(count=Count('pet_id')).order_by('-count')
    pets_by_owner = Pets.objects.values('owner__first_name', 'owner__last_name').annotate(count=Count('pet_id')).order_by('-count')[:10]
    return render(request, 'report_animals.html', {
        'total_pets': total_pets,
        'pets_by_species': pets_by_species,
        'pets_by_owner': pets_by_owner,
    })


@login_required
def report_most_used_medicines(request):
    most_used = Treatments.objects.values('medicine__medicine_name').annotate(total_qty=Sum('quantity')).order_by('-total_qty')[:20]
    total_qty = sum(item['total_qty'] for item in most_used)
    return render(request, 'report_most_used_medicines.html', {
        'most_used': most_used,
        'total_qty': total_qty
    })


@login_required
def pos_receipt(request, bill_id):
    transactions = POSTransaction.objects.filter(bill_id=bill_id).order_by('transaction_date')
    if not transactions:
        return render(request, 'pos_receipt.html', {
            'error': f'ไม่พบใบเสร็จ POS ที่มีรหัส {bill_id}'
        })

    customer_name = 'ไม่ทราบ'
    if transactions:
        customer = Owners.objects.filter(owner_id=transactions[0].customer_id).first()
        if customer:
            customer_name = f'{customer.first_name} {customer.last_name}'

    from decimal import Decimal

    pre_vat = sum(t.total_amount for t in transactions)
    vat = (pre_vat * Decimal('0.07')).quantize(Decimal('0.01'))
    total = (pre_vat + vat).quantize(Decimal('0.01'))

    # ใส่ชื่อยาให้บิล POS
    transactions_with_names = []
    for t in transactions:
        med = Medicines.objects.filter(medicine_id=t.medicine_id).first()
        medicine_name = med.medicine_name if med else t.medicine_id
        transactions_with_names.append({
            'transaction_id': t.transaction_id,
            'medicine_name': medicine_name,
            'quantity': t.quantity,
            'unit_price': t.unit_price,
            'total_amount': t.total_amount,
            'transaction_date': t.transaction_date
        })

    return render(request, 'pos_receipt.html', {
        'bill_id': bill_id,
        'transactions': transactions_with_names,
        'customer_name': customer_name,
        'pre_vat': pre_vat,
        'vat_amount': vat,
        'total': total
    })

@login_required
def pos_receipts_list(request):
    # Get all POS receipts grouped by bill_id
    pos_transactions = POSTransaction.objects.select_related('customer').order_by('-transaction_date')
    
    from collections import defaultdict
    bill_groups = defaultdict(lambda: {'bill_id': None, 'customer_name': '', 'item_count': 0, 'total_amount': 0.0})
    
    for tx in pos_transactions:
        bill_id = tx.bill_id
        if bill_id not in bill_groups:
            customer = tx.customer
            customer_name = f'{customer.first_name} {customer.last_name}' if customer else 'ไม่ทราบ'
            bill_groups[bill_id] = {
                'bill_id': bill_id,
                'customer_name': customer_name,
                'item_count': 0,
                'total_amount': 0.0
            }
        bill_groups[bill_id]['item_count'] += tx.quantity
        bill_groups[bill_id]['total_amount'] += float(tx.total_amount or 0)
    
    pos_receipts = list(bill_groups.values())
    
    return render(request, 'pos_receipts_list.html', {
        'pos_receipts': pos_receipts,
    })

@login_required
def report_pos(request):
    # Get all POS transactions with customer and medicine names
    pos_transactions = POSTransaction.objects.select_related().order_by('-transaction_date')
    
    # Add customer and medicine names to each transaction
    transactions_with_names = []
    for transaction in pos_transactions:
        try:
            customer = Owners.objects.get(owner_id=transaction.customer_id)
            customer_name = f"{customer.first_name} {customer.last_name}"
        except Owners.DoesNotExist:
            customer_name = f"Customer ID: {transaction.customer_id}"
        
        try:
            medicine = Medicines.objects.get(medicine_id=transaction.medicine_id)
            medicine_name = medicine.medicine_name
        except Medicines.DoesNotExist:
            medicine_name = f"Medicine ID: {transaction.medicine_id}"
        
        transactions_with_names.append({
            'transaction_id': transaction.transaction_id,
            'customer_name': customer_name,
            'medicine_name': medicine_name,
            'quantity': transaction.quantity,
            'unit_price': transaction.unit_price,
            'total_amount': transaction.total_amount,
            'transaction_date': transaction.transaction_date
        })
    
    # Calculate totals
    total_sales = sum(t['total_amount'] for t in transactions_with_names)
    total_quantity = sum(t['quantity'] for t in transactions_with_names)
    
    return render(request, 'report_pos.html', {
        'transactions': transactions_with_names,
        'total_sales': total_sales,
        'total_quantity': total_quantity
    })


# AUTH - Logout Management
@login_required
def logout_confirm(request):
    """ยืนยันการออกจากระบบ แล้ว logout โดยตรง"""
    if request.method == 'POST':
        auth_logout(request)
        return redirect('login')
    return render(request, 'logout_confirm.html')


# ================================
# USER MANAGEMENT (Admin Only for Edit/Delete)
# ================================

@login_required
def user_list(request):
    """Display list of all users with search functionality - Everyone can view"""
    search_query = request.GET.get('search', '')
    
    # Get all Django users that are staff/superuser OR have records in CustomUsers
    users = User.objects.filter(
        Q(is_staff=True) | 
        Q(is_superuser=True) | 
        Q(username__in=CustomUsers.objects.values_list('username', flat=True))
    ).distinct()
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Enhance with CustomUsers data if available
    users_data = []
    for user in users.distinct():
        try:
            custom_user = CustomUsers.objects.get(username=user.username)
            role = custom_user.role
            created_at = custom_user.created_at
        except CustomUsers.DoesNotExist:
            # Map Django user flags to our role system: admin, user
            if user.is_superuser:
                role = 'admin'
            else:
                role = 'user'
            created_at = user.date_joined
        
        users_data.append({
            'user': user,
            'role': role,
            'created_at': created_at,
            'is_admin': user.is_superuser,
            'is_staff': user.is_staff
        })
    
    # Determine current user role
    current_user_role = get_user_role(request)
    is_admin = current_user_role == 'admin'

    return render(request, 'users.html', {
        'users_data': users_data,
        'search_query': search_query,
        'is_admin': is_admin
    })


@admin_required
def add_user(request):
    """Create new user account"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'staff')  # admin, staff, user
        
        # Validate required fields
        errors = []
        if not username:
            errors.append('กรุณากรอกชื่อผู้ใช้')
        if not password:
            errors.append('กรุณากรอกรหัสผ่าน')
        if len(password) < 6:
            errors.append('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร')
        
        # Check if staff is creating admin (not allowed)
        current_user_role = get_user_role(request)
        if current_user_role == 'staff' and role == 'admin':
            errors.append('Staff ไม่มีสิทธิ์สร้างผู้ใช้ระดับ Admin')

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            errors.append('ชื่อผู้ใช้นี้มีอยู่ในระบบแล้ว')
        
        if errors:
            return render(request, 'add_user.html', {
                'errors': errors,
                'form_data': request.POST
            })
        
        try:
            # Create Django User with is_staff=True so all users can login
            # Use role in CustomUsers to control actual permissions
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=True,  # Allow all created users to access the system
                is_superuser=True if role == 'admin' else False  # Only admin is superuser
            )
            
            # Create CustomUser record
            try:
                CustomUsers.objects.create(
                    user_id=get_next_id(CustomUsers, 'user_id', 'U'),
                    username=username,
                    password=password,
                    role=role,
                    created_at=datetime.now()
                )
            except Exception as e:
                print(f"Error creating CustomUser: {e}")
            
            return redirect('user_list')
        
        except Exception as e:
            return render(request, 'add_user.html', {
                'errors': [f'เกิดข้อผิดพลาด: {str(e)}'],
                'form_data': request.POST
            })
    
    return render(request, 'add_user.html')


@admin_required
def edit_user(request, username):
    """Edit user details and permissions"""
    user = get_object_or_404(User, username=username)
    custom_user = None
    
    try:
        custom_user = CustomUsers.objects.get(username=username)
    except CustomUsers.DoesNotExist:
        pass

    current_role = get_user_role(request)
    target_role = 'admin' if user.is_superuser else (custom_user.role.strip().lower() if custom_user and custom_user.role else ('staff' if user.is_staff else 'user'))
    if current_role == 'staff' and target_role == 'admin':
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่มีสิทธิ์แก้ไข',
            'error_message': 'Staff ไม่สามารถแก้ไขผู้ใช้งานที่มีสิทธิ์เป็น Admin',
            'error_reason': 'กรุณาให้ Admin แก้ไขสิทธิ์ของผู้ใช้งานระดับ Admin'
        })
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', 'staff')
        new_password = request.POST.get('password', '').strip()
        
        errors = []
        
        # Update user
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_staff = True if role in ['admin', 'staff'] else False
        user.is_superuser = True if role == 'admin' else False
        
        # Update password if provided
        if new_password:
            if len(new_password) < 6:
                errors.append('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร')
            else:
                user.set_password(new_password)
        
        if errors:
            return render(request, 'edit_user.html', {
                'user': user,
                'custom_user': custom_user,
                'errors': errors
            })
        
        try:
            user.save()
            
            # Update custom user role
            if custom_user:
                custom_user.role = role
                custom_user.save()
            
            # Show success message
            return render(request, 'edit_user.html', {
                'user': user,
                'custom_user': custom_user,
                'success': 'บันทึกข้อมูลสำเร็จ'
            })
        
        except Exception as e:
            return render(request, 'edit_user.html', {
                'user': user,
                'custom_user': custom_user,
                'errors': [f'เกิดข้อผิดพลาด: {str(e)}']
            })
    
    return render(request, 'edit_user.html', {
        'user': user,
        'custom_user': custom_user
    })


@admin_required
def delete_user(request, username):
    """Delete a user account (with confirmation)"""
    user = get_object_or_404(User, username=username)

    current_role = get_user_role(request)
    target_is_admin = user.is_superuser or CustomUsers.objects.filter(username=username, role__iexact='admin').exists()
    if current_role == 'staff' and target_is_admin:
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่มีสิทธิ์ลบ',
            'error_message': 'Staff ไม่สามารถลบบัญชีที่เป็น Admin ได้',
            'error_reason': 'กรุณาติดต่อผู้ดูแลระบบระดับสูงเพื่อดำเนินการ'
        })
    
    # Prevent deleting the current logged-in user
    if user.username == request.user.username:
        return render(request, 'error_delete.html', {
            'error_title': '❌ ไม่สามารถลบบัญชีได้',
            'error_message': 'ไม่สามารถลบบัญชีของผู้ใช้ปัจจุบันได้',
            'error_reason': 'โปรดขอให้ผู้ดูแลระบบอื่นลบบัญชีของคุณ'
        })
    
    if request.method == 'POST':
        try:
            # Delete from CustomUsers if exists
            try:
                CustomUsers.objects.filter(username=username).delete()
            except:
                pass
            
            # Delete Django user
            user.delete()
            return redirect('user_list')
        
        except Exception as e:
            return render(request, 'error_delete.html', {
                'error_title': '❌ เกิดข้อผิดพลาด',
                'error_message': f'ไม่สามารถลบผู้ใช้งาน {username} ได้',
                'error_reason': str(e)
            })
    
    # Confirmation page
    return render(request, 'components_delete_modal.html', {
        'title': f'ลบผู้ใช้งาน: {username}',
        'message': f'คุณแน่ใจหรือว่าต้องการลบผู้ใช้งาน {username}?',
        'cancel_url': 'user_list',
        'action_url': f'/users/delete/{username}/'
    })
    