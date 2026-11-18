
from django import forms

from .models import Flashcard


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


class CardEditForm(forms.ModelForm):
    class Meta:
        model = Flashcard
        fields = ["question", "answer", "source_quote"]
        labels = {
            "question": "Вопрос",
            "answer": "Ответ",
            "source_quote": "Цитата из конспекта",
        }
        widgets = {
            "question": forms.TextInput(),
            "answer": forms.Textarea(),
            "source_quote": forms.Textarea(),
        }

    def clean_source_quote(self):
        quote = self.cleaned_data["source_quote"]

        if quote not in self.instance.source.text:
            raise forms.ValidationError(
                "Эта цитата не найдена в исходном конспекте. "
                "Скопируйте точное предложение из материала."
            )

        return quote
