
from django.conf import settings
from django.db import DatabaseError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .demo import DEMO_TEXT, DEMO_TITLE
from .forms import CardEditForm, SourceForm
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

    # Получаем все карточки текущего конспекта
    # в исходном порядке.
    all_cards = source.cards.all().order_by("position", "pk")

    # Счётчики всегда рассчитываются по всему набору.
    total_count = all_cards.count()
    verified_count = all_cards.filter(is_verified=True).count()
    pending_count = total_count - verified_count

    # Получаем и проверяем GET-фильтр.
    status = request.GET.get("status", "all")

    if status not in ("all", "pending", "verified"):
        status = "all"

    # Фильтруем только список отображаемых карточек.
    if status == "pending":
        cards = all_cards.filter(is_verified=False)
    elif status == "verified":
        cards = all_cards.filter(is_verified=True)
    else:
        cards = all_cards

    return render(
        request,
        "study/source_detail.html",
        {
            "source": source,
            "cards": cards,
            "status": status,
            "total_count": total_count,
            "verified_count": verified_count,
            "pending_count": pending_count,
        },
    )


def card_edit(request, pk):
    card = get_object_or_404(
        Flashcard.objects.select_related("source"),
        pk=pk,
    )

    if request.method == "POST":
        form = CardEditForm(request.POST, instance=card)

        if form.is_valid():
            edited_card = form.save(commit=False)
            edited_card.is_verified = False
            edited_card.save()

            return redirect("source_detail", pk=card.source_id)
    else:
        form = CardEditForm(instance=card)

    return render(
        request,
        "study/card_form.html",
        {
            "form": form,
            "card": card,
            "source": card.source,
        },
    )


def card_delete(request, pk):
    card = get_object_or_404(
        Flashcard.objects.select_related("source"),
        pk=pk,
    )

    source_id = card.source_id

    if request.method == "POST":
        card.delete()
        return redirect("source_detail", pk=source_id)

    return render(
        request,
        "study/card_confirm_delete.html",
        {
            "card": card,
            "source": card.source,
        },
    )


@require_POST
def card_review(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)

    action = request.POST.get("action")

    if action == "verify":
        card.is_verified = True
    elif action == "reset":
        card.is_verified = False
    else:
        return HttpResponseBadRequest("Неизвестное действие.")

    card.save(update_fields=["is_verified"])

    return redirect("source_detail", pk=card.source_id)
