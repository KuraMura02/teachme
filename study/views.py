
from django.conf import settings
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .demo import DEMO_TEXT, DEMO_TITLE
from .forms import SourceForm
from .models import Flashcard, Source
from .services import GenerationError, generate_cards


def home(request):
    configured_mode = getattr(settings, "TEACHME_MODE", "demo")
    mode = (
        configured_mode.strip().upper()
        if isinstance(configured_mode, str)
        else "UNKNOWN"
    )

    context = {
        "mode": mode,
        "cards": None,
    }

    if request.method == "POST":
        form = SourceForm(request.POST)

        if form.is_valid():
            text = form.cleaned_data["text"]
            title = form.cleaned_data["title"]

            try:
                cards = generate_cards(text)
            except GenerationError as exc:
                form.add_error(None, str(exc))
            else:
                generation_mode = configured_mode.strip().lower()

                try:
                    with transaction.atomic():
                        source = Source.objects.create(
                            title=title,
                            text=text,
                            generation_mode=generation_mode,
                        )

                        for position, card in enumerate(cards, start=1):
                            Flashcard.objects.create(
                                source=source,
                                position=position,
                                question=card["question"],
                                answer=card["answer"],
                                source_quote=card["source_quote"],
                            )

                except DatabaseError:
                    form.add_error(
                        None,
                        "Не удалось сохранить конспект и карточки. "
                        "Проверьте базу данных и повторите попытку.",
                    )
                else:
                    return redirect("source_detail", pk=source.pk)
    else:
        form = SourceForm(
            initial={
                "title": DEMO_TITLE,
                "text": DEMO_TEXT,
            }
        )

    context["form"] = form
    context["sources"] = Source.objects.order_by("-created_at", "-id")

    return render(request, "study/home.html", context)


def source_detail(request, pk):
    source = get_object_or_404(
        Source.objects.prefetch_related("cards"),
        pk=pk,
    )

    return render(
        request,
        "study/source_detail.html",
        {
            "source": source,
            "cards": source.cards.all(),
        },
    )
