from django import forms
from .models import Product, Category, Review, Coupon

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'slug', 'price', 'old_price', 'image', 'description', 'stock', 'available']

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'slug']

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