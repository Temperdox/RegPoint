from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Event, EventCategory, Registration, TicketType, UserProfile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    phone = forms.CharField(max_length=20, required=False)
    company = forms.CharField(max_length=200, required=False)
    security_question = forms.CharField(
        max_length=200,
        required=True,
        help_text="e.g., What is your pet's name?",
    )
    security_answer = forms.CharField(max_length=200, required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["placeholder"] = field.label or field_name.replace(
                "_", " "
            ).title()


class AllauthSignUpForm(forms.Form):
    """Extra fields injected into the allauth signup form."""

    first_name = forms.CharField(max_length=30, required=True,
                                 widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(max_length=30, required=True,
                                widget=forms.TextInput(attrs={"class": "form-control"}))
    phone = forms.CharField(max_length=20, required=False,
                            widget=forms.TextInput(attrs={"class": "form-control"}))
    company = forms.CharField(max_length=200, required=False,
                              widget=forms.TextInput(attrs={"class": "form-control"}))
    security_question = forms.CharField(
        max_length=200, required=True,
        help_text="e.g., What is your pet's name?",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    security_answer = forms.CharField(
        max_length=200, required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def signup(self, request, user):
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        # Profile is created via signal; update extra fields
        profile = user.profile
        profile.phone = self.cleaned_data.get("phone", "")
        profile.company = self.cleaned_data.get("company", "")
        profile.security_question = self.cleaned_data["security_question"]
        profile.security_answer = self.cleaned_data["security_answer"]
        profile.save()


class EmailOTPForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-lg text-center letter-spacing-wide",
            "placeholder": "000000",
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "pattern": "[0-9]*",
        }),
    )


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ["phone", "company", "bio", "avatar"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["avatar"].widget.attrs["class"] = "form-control"
        self.fields["avatar"].widget.attrs["accept"] = "image/*"


class ChangeUsernameForm(forms.Form):
    new_username = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_user = current_user

    def clean_new_username(self):
        username = self.cleaned_data["new_username"]
        if (
            User.objects.filter(username=username)
            .exclude(pk=self.current_user.pk if self.current_user else None)
            .exists()
        ):
            raise forms.ValidationError("This username is already taken.")
        return username


class ChangeEmailForm(forms.Form):
    new_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )


class IdentityVerifyForm(forms.Form):
    """Form to verify identity before sensitive account changes."""

    method = forms.ChoiceField(
        choices=[
            ("password", "Current password"),
            ("email_otp", "Email verification code"),
            ("sms_otp", "SMS verification code"),
        ],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    credential = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter password or OTP code",
        }),
    )


class AccountRecoveryForm(forms.Form):
    identifier = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Email, username, or phone number",
        }),
        help_text="Enter the email, username, or phone number associated with your account.",
    )


class AccountDeleteForm(forms.Form):
    confirm_text = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": 'Type "DELETE" to confirm',
        }),
    )

    def clean_confirm_text(self):
        text = self.cleaned_data["confirm_text"]
        if text != "DELETE":
            raise forms.ValidationError('You must type "DELETE" to confirm.')
        return text


class AdminUserRoleForm(forms.Form):
    is_staff = forms.BooleanField(required=False, label="Staff access")
    is_superuser = forms.BooleanField(required=False, label="Superuser access")


class EventForm(forms.ModelForm):
    date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        )
    )
    end_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"}
        ),
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "category",
            "date",
            "end_date",
            "location",
            "capacity",
            "price",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = ["name", "price", "quantity_available"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class RegistrationForm(forms.Form):
    ticket_type = forms.ModelChoiceField(
        queryset=TicketType.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if event:
            self.fields["ticket_type"].queryset = event.ticket_types.all()
