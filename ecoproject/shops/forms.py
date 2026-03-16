from django import forms
from .models import Product, Category, Review, Coupon, AfterSalesRequest

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'slug', 'price', 'old_price', 'image', 'description', 'stock', 'available']

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'is_active']

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "content"]
        widgets = {
            "rating": forms.Select(
                choices=[(i, f"{i} ⭐") for i in range(1, 6)],
                attrs={"class": "form-select w-25"}
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Nhập đánh giá của bạn..."
                    }
                )
                }

class CouponForm(forms.Form):
    code = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nhập mã giảm giá (nếu có)'
            })
        )


class CheckoutForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Họ và tên",
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        label="Email",
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Số điện thoại",
    )
    address = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Địa chỉ giao hàng",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not user or not getattr(user, "is_authenticated", False):
            return

        profile = getattr(user, "profile", None)
        self.fields["full_name"].initial = user.get_full_name() or user.username
        self.fields["email"].initial = user.email
        if profile:
            self.fields["phone"].initial = profile.phone
            self.fields["address"].initial = profile.address


class AfterSalesRequestForm(forms.ModelForm):
    class Meta:
        model = AfterSalesRequest
        fields = ["request_type", "reason", "contact_name", "contact_email", "contact_phone"]
        widgets = {
            "request_type": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not order:
            return
        self.fields["contact_name"].initial = order.customer_name
        self.fields["contact_email"].initial = order.customer_email
        self.fields["contact_phone"].initial = order.phone


class AfterSalesRequestUpdateForm(forms.ModelForm):
    class Meta:
        model = AfterSalesRequest
        fields = ["status", "refund_amount", "resolution_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "refund_amount": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 0}),
            "resolution_note": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }


class RefundRequestForm(forms.ModelForm):
    class Meta:
        model = AfterSalesRequest
        fields = ["reason", "contact_name", "contact_email", "contact_phone"]
        widgets = {
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not order:
            return
        self.fields["contact_name"].initial = order.customer_name
        self.fields["contact_email"].initial = order.customer_email
        self.fields["contact_phone"].initial = order.phone
    
class CouponCreateForm(forms.ModelForm):

    class Meta:
        model = Coupon
        fields = [
            'code',
            'discount',
            'max_discount',
            'usage_limit',
            'valid_from',
            'valid_to',
            'categories',
            'active'
        ]

        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_discount': forms.NumberInput(attrs={'class': 'form-control'}),
            'usage_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'valid_from': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'valid_to': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'categories': forms.CheckboxSelectMultiple(),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['valid_from'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['valid_to'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['categories'].queryset = Category.objects.filter(is_active=True).order_by('name')
