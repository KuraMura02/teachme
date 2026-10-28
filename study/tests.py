
from unittest.mock import patch

from django.conf import settings
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from .demo import DEMO_TEXT, DEMO_CARDS
from .models import Flashcard, Source
from .services import GenerationError


class TeachMeTests(TestCase):
    def setUp(self):
        self.home_url = reverse("home")
        self.valid_data = {
            "title": "Компьютерные сети",
            "text": DEMO_TEXT,
        }

    def post_valid_demo(self):
        with patch("study.views.generate_cards", return_value=DEMO_CARDS) as provider:
            response = self.client.post(self.home_url, self.valid_data)
        return response, provider

    def test_valid_demo_post_saves_source_and_three_cards(self):
        response, provider = self.post_valid_demo()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Source.objects.count(), 1)
        self.assertEqual(Flashcard.objects.count(), 3)
        provider.assert_called_once_with(DEMO_TEXT)

        source = Source.objects.get()
        self.assertEqual(source.title, self.valid_data["title"])
        self.assertEqual(source.text, DEMO_TEXT)
        self.assertEqual(
            list(source.cards.order_by("position").values_list("position", flat=True)),
            [1, 2, 3],
        )
        self.assertRedirects(
            response,
            reverse("source_detail", kwargs={"pk": source.pk}),
        )

    def test_short_text_does_not_call_provider_or_save_records(self):
        data = {
            "title": "Короткий текст",
            "text": "Слишком коротко",
        }

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(self.home_url, data)

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)
        self.assertTrue(response.context["form"].is_bound)
        self.assertTrue(response.context["form"].errors)

    
    def test_invalid_quote_rejects_entire_provider_result(self):
        from .services import validate_cards

        invalid_cards = [dict(card) for card in DEMO_CARDS]
        invalid_cards[0]["source_quote"] = "Этой цитаты нет в конспекте"

        with self.assertRaises(GenerationError):
            validate_cards({"cards": invalid_cards}, DEMO_TEXT)

        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)


    def test_generation_error_returns_bound_form_without_saving(self):
        with patch(
            "study.views.generate_cards",
            side_effect=GenerationError("Не удалось создать карточки."),
        ) as provider:
            response = self.client.post(self.home_url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        provider.assert_called_once_with(DEMO_TEXT)
        self.assertTrue(response.context["form"].is_bound)
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)

    def test_database_error_on_second_card_rolls_back_everything(self):
        original_create = Flashcard.objects.create
        calls = {"count": 0}

        def create_with_failure_on_second_card(**kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise DatabaseError("Имитированная ошибка сохранения")
            return original_create(**kwargs)

        with patch(
            "study.views.generate_cards",
            return_value=DEMO_CARDS,
        ), patch(
            "study.views.Flashcard.objects.create",
            side_effect=create_with_failure_on_second_card,
        ):
            response = self.client.post(self.home_url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertEqual(calls["count"], 2)
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)

    def test_two_detail_gets_do_not_call_provider_or_change_database(self):
        source = Source.objects.create(
            title="Сохранённый конспект",
            text=DEMO_TEXT,
            generation_mode=getattr(settings, "TEACHME_MODE", "demo"),
        )
        for position, card in enumerate(DEMO_CARDS, start=1):
            Flashcard.objects.create(
                source=source,
                position=position,
                question=card["question"],
                answer=card["answer"],
                source_quote=card["source_quote"],
            )

        detail_url = reverse("source_detail", kwargs={"pk": source.pk})
        before_sources = Source.objects.count()
        before_cards = Flashcard.objects.count()

        with patch("study.views.generate_cards") as provider:
            first_response = self.client.get(detail_url)
            second_response = self.client.get(detail_url)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        provider.assert_not_called()
        self.assertEqual(Source.objects.count(), before_sources)
        self.assertEqual(Flashcard.objects.count(), before_cards)
        self.assertContains(first_response, "Показать ответ")
        self.assertContains(second_response, "Показать ответ")
