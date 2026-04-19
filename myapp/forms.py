from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Owners as Owner, Pets as Pet, Appointments as Appointment


class CustomLoginForm(AuthenticationForm):
    """Custom login form with Thai error message"""
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            self.user_cache = None
            try:
                from django.contrib.auth import authenticate
                user = authenticate(username=username, password=password)
                if user is None:
                    raise forms.ValidationError(
                        "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง",
                        code='invalid_login',
                    )
                else:
                    self.user_cache = user
            except forms.ValidationError:
                raise
        
        return self.cleaned_data


class OwnerForm(forms.ModelForm):

    class Meta:
        model = Owner
        fields = ['first_name', 'last_name', 'phone', 'email', 'address']
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone or phone.strip() == '':
            raise forms.ValidationError('เบอร์โทรศัพท์เป็นฟิลด์ที่จำเป็น กรุณาใส่เบอร์โทรศัพท์')
        
        # ลบเครื่องหมายขีด ช่องว่าง และอักษรอื่นๆ เก็บแค่ตัวเลข
        cleaned_phone = ''.join(filter(str.isdigit, str(phone)))
        
        if len(cleaned_phone) != 10:
            raise forms.ValidationError('เบอร์โทรศัพท์ต้องมีจำนวน 10 หลักพอดี')
        
        return cleaned_phone
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # อีเมลไม่จำเป็น (สามารถเว้นได้)
        if email and email.strip():
            # ตรวจสอบรูปแบบอีเมล
            if '@' not in email or '.' not in email:
                raise forms.ValidationError('รูปแบบอีเมลไม่ถูกต้อง')
        return email or None


class PetForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = '__all__'
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'})
        }

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight is not None and weight > 1000:
            raise forms.ValidationError('น้ำหนักต้องไม่เกิน 1000 กิโลกรัม')
        return weight


class AppointmentForm(forms.ModelForm):

    class Meta:
        model = Appointment
        fields = '__all__'