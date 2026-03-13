from .models import Profile
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password



class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('photo', 'phone', 'address')
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Repeat password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'email')

    def clean_password2(self):
        cd = self.cleaned_data
        if cd['password'] != cd['password2']:
            raise forms.ValidationError('Passwords don\'t match.')
        return cd['password2']


class PasswordResetOTPRequestForm(forms.Form):
    email = forms.EmailField(label="Email", max_length=254)


class PasswordResetOTPVerifyForm(forms.Form):
    email = forms.EmailField(label="Email", max_length=254)
    otp = forms.CharField(label="OTP", max_length=6, min_length=6)

    def clean_otp(self):
        return self.cleaned_data["otp"].strip()


class PasswordResetOTPSetPasswordForm(forms.Form):
    new_password1 = forms.CharField(label="Mật khẩu mới", widget=forms.PasswordInput)
    new_password2 = forms.CharField(label="Nhập lại mật khẩu", widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("new_password1")
        password2 = cleaned_data.get("new_password2")

        if password1 and password2 and password1 != password2:
            self.add_error("new_password2", "Mật khẩu nhập lại không khớp.")

        if password1 and self.user:
            try:
                validate_password(password1, user=self.user)
            except forms.ValidationError as exc:
                self.add_error("new_password1", exc)

        return cleaned_data
