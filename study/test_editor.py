
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from .demo import DEMO_TEXT
from .models import Flashcard, Source


class CardEditorTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(
            title="Компьютерные сети",
            text=DEMO_TEXT,
            generation_mode=getattr(
                settings,
                "TEACHME_MODE",
                "demo",
            ),
        )

        self.other_source = Source.objects.create(
            title="Другой конспект",
            text=DEMO_TEXT,
            generation_mode="demo",
        )

        self.card = self.create_card(
            self.source,
            position=1,
            question="Что такое DNS?",
            answer="DNS преобразует доменные имена в IP-адреса.",
            source_quote="DNS",
        )

        self.neighbor = self.create_card(
            self.source,
            position=2,
            question="Что такое IP?",
            answer="IP используется для адресации устройств.",
            source_quote="IP",
        )

        self.other_card = self.create_card(
            self.other_source,
            position=1,
            question="Что такое HTTP?",
            answer="HTTP является протоколом передачи данных.",
            source_quote="HTTP",
            is_verified=True,
        )

        self.source_url = reverse(
            "source_detail",
            kwargs={"pk": self.source.pk},
        )

        self.edit_url = reverse(
            "card_edit",
            kwargs={"pk": self.card.pk},
        )

        self.delete_url = reverse(
            "card_delete",
            kwargs={"pk": self.card.pk},
        )

        self.review_url = reverse(
            "card_review",
            kwargs={"pk": self.card.pk},
        )

        self.valid_edit_data = {
            "question": "Как работает DNS?",
            "answer": "DNS сопоставляет доменное имя с IP-адресом.",
            "source_quote": "DNS",
        }

    def create_card(
        self,
        source,
        position,
        question,
        answer,
        source_quote,
        is_verified=False,
    ):
        return Flashcard.objects.create(
            source=source,
            position=position,
            question=question,
            answer=answer,
            source_quote=source_quote,
            is_verified=is_verified,
        )

    def test_edit_get_does_not_write_or_generate_cards(self):
        before_count = Flashcard.objects.count()
        before_question = self.card.question
        before_answer = self.card.answer
        before_quote = self.card.source_quote
        before_verified = self.card.is_verified

        with patch("study.views.generate_cards") as provider:
            response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()

        self.card.refresh_from_db()

        self.assertEqual(Flashcard.objects.count(), before_count)
        self.assertEqual(self.card.question, before_question)
        self.assertEqual(self.card.answer, before_answer)
        self.assertEqual(self.card.source_quote, before_quote)
        self.assertEqual(self.card.is_verified, before_verified)

    def test_valid_edit_changes_card_and_resets_verification(self):
        self.card.is_verified = True
        self.card.save(update_fields=["is_verified"])

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(
                self.edit_url,
                self.valid_edit_data,
            )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.source_url)
        provider.assert_not_called()

        self.card.refresh_from_db()

        self.assertEqual(
            self.card.question,
            self.valid_edit_data["question"],
        )
        self.assertEqual(
            self.card.answer,
            self.valid_edit_data["answer"],
        )
        self.assertEqual(
            self.card.source_quote,
            self.valid_edit_data["source_quote"],
        )
        self.assertFalse(self.card.is_verified)

    def test_empty_fields_are_rejected_without_saving(self):
        empty_fields = [
            "question",
            "answer",
            "source_quote",
        ]

        with patch("study.views.generate_cards") as provider:
            for field in empty_fields:
                with self.subTest(field=field):
                    data = self.valid_edit_data.copy()
                    data[field] = ""

                    response = self.client.post(
                        self.edit_url,
                        data,
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["form"].errors)

                    self.card.refresh_from_db()

                    self.assertEqual(
                        self.card.question,
                        "Что такое DNS?",
                    )
                    self.assertEqual(
                        self.card.answer,
                        "DNS преобразует доменные имена в IP-адреса.",
                    )
                    self.assertEqual(self.card.source_quote, "DNS")

        provider.assert_not_called()

    def test_question_longer_than_300_characters_is_rejected(self):
        data = self.valid_edit_data.copy()
        data["question"] = "В" * 301

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(self.edit_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "question",
            response.context["form"].errors,
        )
        provider.assert_not_called()

        self.card.refresh_from_db()

        self.assertEqual(self.card.question, "Что такое DNS?")
        self.assertEqual(Flashcard.objects.count(), 3)

    def test_quote_not_found_in_source_is_rejected(self):
        data = self.valid_edit_data.copy()
        data["source_quote"] = "Этого текста нет в конспекте"

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(self.edit_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "source_quote",
            response.context["form"].errors,
        )
        provider.assert_not_called()

        self.card.refresh_from_db()

        self.assertEqual(self.card.source_quote, "DNS")
        self.assertEqual(Flashcard.objects.count(), 3)

    def test_post_cannot_change_source_position_or_verified_status(self):
        data = self.valid_edit_data.copy()
        data.update({
            "source": self.other_source.pk,
            "position": 99,
            "is_verified": "true",
        })

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(self.edit_url, data)

        self.assertEqual(response.status_code, 302)
        provider.assert_not_called()

        self.card.refresh_from_db()

        self.assertEqual(self.card.source_id, self.source.pk)
        self.assertEqual(self.card.position, 1)
        self.assertFalse(self.card.is_verified)
        self.assertEqual(
            self.card.question,
            self.valid_edit_data["question"],
        )

    def test_delete_get_and_cancel_do_not_delete_records(self):
        before_cards = Flashcard.objects.count()
        before_sources = Source.objects.count()

        with patch("study.views.generate_cards") as provider:
            response = self.client.get(self.delete_url)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Да, удалить")

            self.card.refresh_from_db()
            self.assertEqual(Flashcard.objects.count(), before_cards)

            cancel_response = self.client.get(self.source_url)

            self.assertEqual(cancel_response.status_code, 200)

        provider.assert_not_called()

        self.assertEqual(Flashcard.objects.count(), before_cards)
        self.assertEqual(Source.objects.count(), before_sources)
        self.assertTrue(
            Flashcard.objects.filter(pk=self.card.pk).exists()
        )
        self.assertTrue(
            Source.objects.filter(pk=self.source.pk).exists()
        )

    def test_delete_post_removes_only_selected_card(self):
        card_id = self.card.pk
        neighbor_id = self.neighbor.pk
        source_id = self.source.pk

        with patch("study.views.generate_cards") as provider:
            response = self.client.post(self.delete_url)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "source_detail",
                kwargs={"pk": source_id},
            ),
        )
        provider.assert_not_called()

        self.assertFalse(
            Flashcard.objects.filter(pk=card_id).exists()
        )
        self.assertTrue(
            Flashcard.objects.filter(pk=neighbor_id).exists()
        )
        self.assertTrue(
            Source.objects.filter(pk=source_id).exists()
        )
        self.assertEqual(
            Flashcard.objects.filter(source_id=source_id).count(),
            1,
        )

    def test_review_get_returns_405(self):
        with patch("study.views.generate_cards") as provider:
            response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 405)
        provider.assert_not_called()

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_verified)

    def test_review_verify_reset_and_repeated_verify(self):
        with patch("study.views.generate_cards") as provider:
            first_response = self.client.post(
                self.review_url,
                {"action": "verify"},
            )

            self.assertEqual(first_response.status_code, 302)

            self.card.refresh_from_db()
            self.assertTrue(self.card.is_verified)

            second_response = self.client.post(
                self.review_url,
                {"action": "verify"},
            )

            self.assertEqual(second_response.status_code, 302)

            self.card.refresh_from_db()
            self.assertTrue(self.card.is_verified)

            reset_response = self.client.post(
                self.review_url,
                {"action": "reset"},
            )

            self.assertEqual(reset_response.status_code, 302)

        provider.assert_not_called()

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_verified)

    def test_unknown_review_action_returns_400_without_saving(self):
        with patch("study.views.generate_cards") as provider:
            response = self.client.post(
                self.review_url,
                {"action": "unknown"},
            )

        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_verified)

    def test_filters_show_only_cards_from_current_source(self):
        self.card.is_verified = False
        self.card.save(update_fields=["is_verified"])

        self.neighbor.is_verified = True
        self.neighbor.save(update_fields=["is_verified"])

        self.create_card(
            self.other_source,
            position=2,
            question="Вторая карточка другого конспекта",
            answer="Ответ",
            source_quote="конспекта",
            is_verified=False,
        )

        all_url = self.source_url
        pending_url = f"{self.source_url}?status=pending"
        verified_url = f"{self.source_url}?status=verified"

        with patch("study.views.generate_cards") as provider:
            all_response = self.client.get(all_url)
            pending_response = self.client.get(pending_url)
            verified_response = self.client.get(verified_url)

        provider.assert_not_called()

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(verified_response.status_code, 200)

        for response in (
            all_response,
            pending_response,
            verified_response,
        ):
            self.assertEqual(response.context["total_count"], 2)
            self.assertEqual(response.context["verified_count"], 1)
            self.assertEqual(response.context["pending_count"], 1)

        all_ids = list(
            all_response.context["cards"].values_list("pk", flat=True)
        )
        pending_ids = list(
            pending_response.context["cards"].values_list("pk", flat=True)
        )
        verified_ids = list(
            verified_response.context["cards"].values_list("pk", flat=True)
        )

        self.assertEqual(
            all_ids,
            [self.card.pk, self.neighbor.pk],
        )
        self.assertEqual(pending_ids, [self.card.pk])
        self.assertEqual(verified_ids, [self.neighbor.pk])

        self.assertEqual(all_response.context["status"], "all")
        self.assertEqual(pending_response.context["status"], "pending")
        self.assertEqual(verified_response.context["status"], "verified")

    def test_unknown_filter_value_displays_all_cards(self):
        with patch("study.views.generate_cards") as provider:
            response = self.client.get(
                f"{self.source_url}?status=unknown"
            )

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()

        self.assertEqual(response.context["status"], "all")
        self.assertEqual(
            response.context["cards"].count(),
            2,
        )
        self.assertEqual(response.context["total_count"], 2)

    def test_empty_pending_filter_has_show_all_link(self):
        self.card.is_verified = True
        self.card.save(update_fields=["is_verified"])

        self.neighbor.is_verified = True
        self.neighbor.save(update_fields=["is_verified"])

        with patch("study.views.generate_cards") as provider:
            response = self.client.get(
                f"{self.source_url}?status=pending"
            )

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()

        self.assertEqual(response.context["total_count"], 2)
        self.assertEqual(response.context["verified_count"], 2)
        self.assertEqual(response.context["pending_count"], 0)
        self.assertEqual(response.context["cards"].count(), 0)

        self.assertContains(
            response,
            "В этом фильтре пока нет карточек.",
        )
        self.assertContains(
            response,
            'href="?status=all"',
        )
        self.assertContains(response, "Показать все")

    def test_empty_source_keeps_source_text_visible(self):
        empty_source = Source.objects.create(
            title="Пустой конспект",
            text="Текст сохранённого конспекта.",
            generation_mode="demo",
        )

        empty_url = reverse(
            "source_detail",
            kwargs={"pk": empty_source.pk},
        )

        with patch("study.views.generate_cards") as provider:
            response = self.client.get(
                f"{empty_url}?status=pending"
            )

        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()

        self.assertEqual(response.context["total_count"], 0)
        self.assertEqual(response.context["verified_count"], 0)
        self.assertEqual(response.context["pending_count"], 0)
        self.assertEqual(response.context["cards"].count(), 0)

        self.assertContains(
            response,
            "В этом наборе пока нет учебных карточек.",
        )
        self.assertContains(
            response,
            "Текст сохранённого конспекта.",
        )

    def test_unknown_card_and_source_ids_return_404(self):
        missing_pk = 999999

        get_urls = [
            reverse("card_edit", kwargs={"pk": missing_pk}),
            reverse("card_delete", kwargs={"pk": missing_pk}),
            reverse("source_detail", kwargs={"pk": missing_pk}),
        ]

        review_url = reverse(
            "card_review",
            kwargs={"pk": missing_pk},
        )

        with patch("study.views.generate_cards") as provider:
            for url in get_urls:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 404)

            review_response = self.client.post(
                review_url,
                {"action": "verify"},
            )   

            self.assertEqual(review_response.status_code, 404)

        provider.assert_not_called()

    def test_edit_post_without_csrf_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)

        with patch("study.views.generate_cards") as provider:
            response = csrf_client.post(
                self.edit_url,
                self.valid_edit_data,
            )

        self.assertEqual(response.status_code, 403)
        provider.assert_not_called()

        self.card.refresh_from_db()
        self.assertEqual(self.card.question, "Что такое DNS?")

    def test_delete_post_without_csrf_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)

        with patch("study.views.generate_cards") as provider:
            response = csrf_client.post(self.delete_url)

        self.assertEqual(response.status_code, 403)
        provider.assert_not_called()

        self.assertTrue(
            Flashcard.objects.filter(pk=self.card.pk).exists()
        )

    def test_review_post_without_csrf_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)

        with patch("study.views.generate_cards") as provider:
            response = csrf_client.post(
                self.review_url,
                {"action": "verify"},
            )

        self.assertEqual(response.status_code, 403)
        provider.assert_not_called()

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_verified)
