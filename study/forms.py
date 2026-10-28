
from django import forms


class SourceForm(forms.Form):
    title = forms.CharField(
        max_length=120,
        required=True,
        strip=True,
        label="Тема",
    )
    text = forms.CharField(
        min_length=80,
        max_length=12000,
        required=True,
        strip=True,
        label="Текст материала",
        widget=forms.Textarea,
    )

    def clean_text(self):
        text = self.cleaned_data["text"]
        return text.replace("\r\n", "\n").replace("\r", "\n")
