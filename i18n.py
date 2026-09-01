"""
i18n.py — локализация аддона Anker (русский / английский).

Язык хранится в config.json аддона (ключ "language": "ru" | "en").
Модуль читает этот файл напрямую с кэшем по mtime — поэтому работает
одинаково и внутри Anki (после mw.addonManager.writeConfig mtime меняется
и кэш обновляется сам), и в чистых тестах без aqt.

t(key, **kwargs) возвращает строку на текущем языке; неизвестный ключ
возвращается как есть (падение интерфейса из-за перевода исключено).
"""

import json
import os

LANG_RU = "ru"
LANG_EN = "en"

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

STRINGS = {
    # ─────────────────────────── РУССКИЙ ───────────────────────────
    "ru": {
        # Общие
        "unit_days": " дн.",
        "no_data": "Нет данных",

        # Вкладки и навигация
        "tab_main": "Главное",
        "tab_summary": "Итог",
        "tab_all": "Все показатели",
        "btn_back": "Назад",
        "btn_done": "Готово",
        "btn_cancel": "Отмена",

        # Кнопка статистики в основном диалоге
        "stats_btn_default": "Моя статистика",
        "stats_btn_deck": "Статистика {deck_name} ({period} дн.)",

        # Названия показателей
        "m_true_retention": "Вспоминаемость",
        "m_new_card_retention": "Новые карточки",
        "m_avg_difficulty": "Средняя сложность",
        "m_avg_stability": "Средняя стабильность",
        "m_low_stability_ratio": "Доля нестабильных",
        "m_actual_vs_predicted": "Факт и прогноз",
        "m_avg_time_growth": "Время на карточку",
        "m_consistency": "Регулярность",
        "m_relearning_stuck": "Застрявшие",
        "m_relearning_stuck_full": "Застрявшие карточки",
        "m_again_young": "Доля ошибок (новые)",
        "m_again_mature": "Доля ошибок (зрелые)",

        # Пояснения: вспоминаемость
        "expl_retention_none": "Недостаточно данных для оценки вспоминаемости.",
        "expl_retention_low": "Вспоминаемость ниже 50% значит, что большая часть слов забывается и требует повторного изучения почти с нуля.",
        "expl_retention_mid": "Вспоминаемость 50–70% — материал усваивается, но значительная часть карточек требует повторных усилий.",
        "expl_retention_good": "Вспоминаемость 70–85% — хороший уровень. Большинство карточек вспоминается уверенно, но есть куда расти.",
        "expl_retention_high": "Вспоминаемость выше 85% — отличный результат. Материал усваивается уверенно, можно подумать об увеличении нагрузки.",

        # Пояснения: доля ошибок
        "expl_again_none": "Недостаточно данных для оценки доли повторных ошибок.",
        "expl_again_high": "Доля ошибок выше 25% — признак перегрузки. Слишком много карточек приходится переучивать заново.",
        "expl_again_mid": "Доля ошибок 15–25% — повышенный уровень. Часть материала забывается быстрее, чем хотелось бы.",
        "expl_again_norm": "Доля ошибок 8–15% — нормальный рабочий уровень. Большинство повторений проходит успешно.",
        "expl_again_low": "Доля ошибок ниже 8% — отлично. Карточки вспоминаются легко и без усилий.",

        # Пояснения: сложность
        "expl_diff_none": "Недостаточно данных для оценки сложности карточек.",
        "expl_diff_high": "Средняя сложность выше 7 — карточки объективно трудные. Стоит снизить темп добавления новых.",
        "expl_diff_mid": "Средняя сложность 5–7 — умеренный уровень. Карточки требуют внимания, но не чрезмерно.",
        "expl_diff_low": "Средняя сложность ниже 5 — карточки относительно лёгкие. Можно уверенно добавлять новый материал.",

        # Пояснения: стабильность
        "expl_stab_none": "Недостаточно данных для оценки стабильности.",
        "expl_stab_low": "Стабильность ниже 3 дней — карточки быстро забываются, интервалы короткие.",
        "expl_stab_mid": "Стабильность 3–10 дней — нормальный уровень, карточки закрепляются.",
        "expl_stab_high": "Стабильность выше 10 дней — отлично, интервалы между повторениями большие.",

        # Пояснения: факт и прогноз
        "expl_load_none": "Недостаточно данных для сравнения нагрузки.",
        "expl_load_high": "Фактическая нагрузка заметно выше прогноза — лимит, возможно, завышен.",
        "expl_load_mid": "Фактическая нагрузка немного выше прогноза.",
        "expl_load_norm": "Фактическая нагрузка близка к прогнозу — всё в порядке.",
        "expl_load_low": "Фактическая нагрузка ниже прогноза.",

        # Пояснения: время на карточку
        "expl_time_none": "Недостаточно данных о времени на карточку.",
        "expl_time_high": "На карточки стало уходить заметно больше времени, чем раньше, — возможно, ты устаёшь.",
        "expl_time_mid": "Время на карточку немного выросло по сравнению с прошлым периодом.",
        "expl_time_norm": "Время на карточку стабильно — без резких скачков вверх или вниз.",
        "expl_time_low": "Время на карточку снижается — материал усваивается быстрее.",

        # Пояснения: регулярность
        "expl_consist_none": "Недостаточно данных о регулярности занятий.",
        "expl_consist_low": "Регулярность низкая — занятия проходят нестабильно, это мешает закреплению.",
        "expl_consist_mid": "Регулярность средняя — есть пропуски, но в целом ритм держится.",
        "expl_consist_high": "Регулярность высокая — стабильный график занятий.",

        # Пояснения: застрявшие
        "expl_stuck_none": "Нет данных о застрявших карточках.",
        "expl_stuck_high": "Много карточек застряло в переучивании — стоит обратить на них внимание.",
        "expl_stuck_mid": "Несколько карточек застряло в переучивании.",
        "expl_stuck_low": "Застрявших карточек мало или нет.",

        # Пояснения: новые карточки
        "expl_newret_none": "Недостаточно данных по новым карточкам.",
        "expl_newret_low": "Новые карточки запоминаются тяжело — больше половины забывается.",
        "expl_newret_mid": "Новые карточки усваиваются средне.",
        "expl_newret_good": "Новые карточки усваиваются хорошо.",
        "expl_newret_high": "Новые карточки усваиваются отлично.",

        # Пояснения: доля нестабильных
        "expl_lowstab_none": "Недостаточно данных о нестабильных карточках.",
        "expl_lowstab_high": "Много карточек с низкой стабильностью — материал ещё не закрепился.",
        "expl_lowstab_mid": "Умеренная доля нестабильных карточек.",
        "expl_lowstab_low": "Мало нестабильных карточек — материал закрепляется хорошо.",

        # Подписи под графиками
        "cap_true_retention": "На графике — вспоминаемость по дням, в процентах.",
        "cap_new_card_retention": "Шкала показывает долю успешно вспомненных новых карточек (0–100%). Считается за последние 30 дней — не зависит от периода анализа.",
        "cap_avg_difficulty": "Шкала показывает текущий уровень сложности от 0 до 10.",
        "cap_avg_stability": "Шкала показывает стабильность карточек — количество дней, за которое вспоминаемость падает до 90%.",
        "cap_low_stability_ratio": "Показывает, какая доля карточек ещё нестабильна (могут забыться быстро).",
        "cap_actual_vs_predicted": "Сравнение количества повторений: ожидаемое и фактическое.",
        "cap_avg_time_growth": "Сравнение среднего времени на карточку: раньше и сейчас (в секундах).",
        "cap_consistency": "На графике — количество карточек, пройденных в этот день.",
        "cap_relearning_stuck": "На диаграмме — сколько из карточек, пройденных сегодня, застряло, а сколько в порядке.",
        "donut_stuck": "Застряли",
        "donut_ok": "В порядке",
        "chart_empty_note": "Сегодня ещё нет пройденных карточек для этого графика.",

        # Подписи парных столбцов
        "lbl_expected": "Ожидалось",
        "lbl_actual": "Фактически",
        "lbl_before": "Раньше",
        "lbl_now": "Сейчас",

        # Примечание и вкладка «Итог»
        "stats_note": "Ниже представлены показатели за {period} дн. Они могут отличаться от общей статистики Anki.",
        "summary_subtitle": "Оценка статистики за {period} дн.",
        "sum_comment_1": "Сейчас тебе непросто — материал плохо закрепляется, и это чувствуется. Ничего страшного, бывает у всех. Стоит притормозить и меньше нагружать себя, пока не наверстаешь.",
        "sum_comment_2": "Результаты сейчас ниже обычного — часть материала выветривается быстрее, чем хотелось бы. Стоит немного сбавить темп и уделить время повторению того, что уже проходил.",
        "sum_comment_3": "Ты держишься в целом нормально — ничего критичного, но и без большого запаса прочности. Есть куда расти, если добавить чуть больше внимания к повторениям.",
        "sum_comment_4": "У тебя хорошо получается — материал закрепляется уверенно, сбоев почти нет. Продолжай в том же духе.",
        "sum_comment_5": "Отличный результат — ты закрепляешь материал очень уверенно и стабильно. Можно даже немного ускориться, если хочется двигаться быстрее.",
        "sum_cmp_better": "Стало заметно лучше, чем в прошлый раз (было {prev}/10)",
        "sum_cmp_worse": "Немного просело по сравнению с прошлым разом (было {prev}/10)",
        "sum_cmp_same": "Держится примерно на том же уровне (было {prev}/10)",
        "rec_title": "Что можно улучшить",
        "rec_empty": "Явных слабых мест не видно — можно просто продолжать в том же духе.",
        "rec_true_retention": "Уделяй чуть больше внимания повторениям — вспоминаемость сейчас ниже, чем хотелось бы.",
        "rec_new_card_retention": "Не спеши добавлять много новых карточек сразу — дай свежим словам закрепиться получше.",
        "rec_avg_difficulty": "Многие карточки объективно трудные — попробуй снизить темп добавления новых на время.",
        "rec_avg_stability": "Часть материала пока нестабильна в памяти — не лишним будет вернуться к нему через повторение.",
        "rec_low_stability_ratio": "Заметная доля карточек ещё не закрепилась прочно — им нужно больше времени и внимания.",
        "rec_actual_vs_predicted": "Нагрузка ощутимо выше, чем задумано, — стоит пересмотреть лимит новых карточек.",
        "rec_avg_time_growth": "На карточки уходит больше времени, чем раньше, — возможно, стоит сделать паузу или снизить темп.",
        "rec_consistency": "Занятия проходят нерегулярно — постарайся заниматься примерно в одном ритме, это помогает лучше запоминать.",
        "rec_relearning_stuck": "Немало карточек застряло в переучивании — стоит отдельно поработать именно над ними.",

        # Дни недели
        "day_1": "Пн",
        "day_2": "Вт",
        "day_3": "Ср",
        "day_4": "Чт",
        "day_5": "Пт",
        "day_6": "Сб",
        "day_7": "Вс",

        # Диалоги маскота
        "dlg_days_title": "Anker — дни недели",
        "pv_increase_msg": "Ты уверенно справляешься с колодой «{deck_name}» — можно немного ускориться и добавить новых карточек.",
        "pv_increase_yes": "Да, давай увеличим",
        "pv_increase_no": "Пока оставим как есть",
        "pv_decrease_msg": "Тебе в последнее время нелегко даются повторения колоды «{deck_name}». Есть смысл ненадолго снизить количество новых карточек, чтобы закрепить то, что уже выучено.",
        "pv_decrease_yes": "Да, давай снизим",
        "pv_decrease_no": "Нет, я справлюсь",
        "pv_stable_msg": "Ты стабильно хорошо закрепляешь материал колоды «{deck_name}» — и уже не первую неделю. Не расслабляйся, но темп отличный!",
        "pv_stable_btn": "Спасибо!",
        "pv_neutral_msg": "У тебя всё ровно с колодой «{deck_name}» — продолжай в своём темпе.",
        "pv_neutral_btn": "Хорошо",
        "an_msg": "Сегодня тебе явно тяжелее обычного даётся «{deck_name}». Что случилось?",
        "an_lazy": "Лень / не хочется",
        "an_busy": "Занят(а) сегодня",
        "an_dismiss": "Само пройдёт",
        "lazy_msg": "Бывает у всех, не переживай. Давай включим для тебя временный лёгкий режим по «{deck_name}» — я ненадолго снижу количество новых карточек, а потом всё вернётся как было.",
        "lazy_3": "Лёгкий режим на 3 дня",
        "lazy_5": "Лёгкий режим на 5 дней",
        "lazy_7": "Лёгкий режим на 7 дней",
        "lazy_no": "Не надо, я в порядке",
        "busy_msg": "Понимаю, бывают такие дни. Хочешь, я настрою для тебя дни недели без новых карточек по «{deck_name}»?",
        "busy_setup": "Настроить дни недели",
        "busy_skip": "Не сегодня",
        "days_msg": "В какие дни тебе обычно не до новых карточек по «{deck_name}»? Отметь их — я подстроюсь.",

        # Выбор колод
        "ds_title": "Anker — выбор колод",
        "ds_warning": "⚠ Некоторые колоды вложены друг в друга — это приведёт к двойному учёту карточек. Оставьте только родительскую колоду.",
        "ds_search": "Поиск колоды…",
        "ds_all": "Выбрать все",
        "ds_none": "Снять все",
        "ds_conflict": "Нельзя выбрать родительскую и дочернюю колоду одновременно. Оставьте только родительскую.",

        # Меню и служебные сообщения
        "menu_settings": "Настройки…",
        "menu_decks": "Выбрать колоды…",
        "menu_force": "Запустить анализ сейчас (тест)",
        "menu_mascot": "Показать маскота (тест)",
        "menu_reset": "Сбросить состояние",
        "lang_label": "Выбери язык интерфейса:",
        "lang_set_ru": "Anker: язык интерфейса — русский.",
        "lang_set_en": "Anker: interface language — English.",
        "set_title": "Anker — настройки",
        "set_label": "Период анализа (дней):\nОпределяет, как часто Anker проверяет статистику\nи за какой промежуток она считается.",
        "set_saved": "Anker: период анализа — {period} дн.",
        "tt_decks": "Anker: выбрано колод — {n}",
        "msg_no_deck": "Нет выбранной колоды. Выберите хотя бы одну колоду для теста в настройках Anker: Anker → Выбрать колоды…",
        "msg_history": "Колода «{deck_name}»: недостаточно истории — нужно минимум {min_days} дн., сейчас {actual_days}.\n\nСовет: для быстрой проверки можно временно занизить min_history_days в конфиге аддона (например, до 1).",
        "tt_light": "Anker: лёгкий режим для «{deck_name}» на {days} дн.",
        "tt_limit_up": "Anker: лимит повышен, новый ≈ {target}",
        "tt_limit_down": "Anker: лимит снижен, новый ≈ {target}",
        "tt_limit_err": "Anker: не удалось изменить лимит колоды: {err}",
        "tt_reset": "Anker: состояние сброшено, выбор колод очищен.",
        "msg_save_err": "Не удалось сохранить настройки: {err}",
        "tt_test": "Anker: тестовое действие: {action}",
        "test_reason": "Тестовый запуск.",
    },

    # ─────────────────────────── ENGLISH ───────────────────────────
    "en": {
        # Common
        "unit_days": " d",
        "no_data": "No data",

        # Tabs and navigation
        "tab_main": "Main",
        "tab_summary": "Summary",
        "tab_all": "All metrics",
        "btn_back": "Back",
        "btn_done": "Done",
        "btn_cancel": "Cancel",

        # Statistics button in the main dialog
        "stats_btn_default": "My statistics",
        "stats_btn_deck": "Statistics: {deck_name} ({period} d)",

        # Metric names
        "m_true_retention": "Recall",
        "m_new_card_retention": "New cards",
        "m_avg_difficulty": "Average difficulty",
        "m_avg_stability": "Average stability",
        "m_low_stability_ratio": "Unstable share",
        "m_actual_vs_predicted": "Actual vs predicted",
        "m_avg_time_growth": "Time per card",
        "m_consistency": "Regularity",
        "m_relearning_stuck": "Stuck",
        "m_relearning_stuck_full": "Stuck cards",
        "m_again_young": "Error rate (young)",
        "m_again_mature": "Error rate (mature)",

        # Explanations: recall
        "expl_retention_none": "Not enough data to assess recall.",
        "expl_retention_low": "Recall below 50% means most words are forgotten and have to be relearned almost from scratch.",
        "expl_retention_mid": "Recall of 50–70% — the material is being absorbed, but a significant share of cards takes repeated effort.",
        "expl_retention_good": "Recall of 70–85% is a good level. Most cards are recalled confidently, but there's room to grow.",
        "expl_retention_high": "Recall above 85% is an excellent result. The material is sticking well — you could consider increasing the load.",

        # Explanations: error rate
        "expl_again_none": "Not enough data to assess the share of repeat mistakes.",
        "expl_again_high": "An error rate above 25% is a sign of overload. Too many cards have to be relearned from scratch.",
        "expl_again_mid": "An error rate of 15–25% is elevated. Some material is forgotten faster than you'd like.",
        "expl_again_norm": "An error rate of 8–15% is a normal working level. Most reviews go successfully.",
        "expl_again_low": "An error rate below 8% is excellent. Cards come to mind easily and effortlessly.",

        # Explanations: difficulty
        "expl_diff_none": "Not enough data to assess card difficulty.",
        "expl_diff_high": "Average difficulty above 7 — the cards are genuinely hard. It's worth slowing down on adding new ones.",
        "expl_diff_mid": "Average difficulty of 5–7 is a moderate level. Cards require attention, but not excessively.",
        "expl_diff_low": "Average difficulty below 5 — the cards are relatively easy. You can confidently add new material.",

        # Explanations: stability
        "expl_stab_none": "Not enough data to assess stability.",
        "expl_stab_low": "Stability below 3 days — cards are forgotten quickly, intervals are short.",
        "expl_stab_mid": "Stability of 3–10 days is a normal level, cards are consolidating.",
        "expl_stab_high": "Stability above 10 days is excellent — intervals between reviews are long.",

        # Explanations: actual vs predicted
        "expl_load_none": "Not enough data to compare workload.",
        "expl_load_high": "Actual workload is noticeably higher than predicted — the limit may be set too high.",
        "expl_load_mid": "Actual workload is slightly higher than predicted.",
        "expl_load_norm": "Actual workload is close to predicted — everything is fine.",
        "expl_load_low": "Actual workload is below predicted.",

        # Explanations: time per card
        "expl_time_none": "Not enough data on time per card.",
        "expl_time_high": "Cards have been taking noticeably more time than before — you may be getting tired.",
        "expl_time_mid": "Time per card has grown a little compared to the previous period.",
        "expl_time_norm": "Time per card is stable — no sharp jumps up or down.",
        "expl_time_low": "Time per card is going down — the material is being absorbed faster.",

        # Explanations: regularity
        "expl_consist_none": "Not enough data about study regularity.",
        "expl_consist_low": "Regularity is low — sessions are erratic, which gets in the way of consolidation.",
        "expl_consist_mid": "Regularity is average — there are skipped days, but the rhythm mostly holds.",
        "expl_consist_high": "Regularity is high — a steady study schedule.",

        # Explanations: stuck cards
        "expl_stuck_none": "No data on stuck cards.",
        "expl_stuck_high": "Many cards are stuck in relearning — worth paying attention to them.",
        "expl_stuck_mid": "A few cards are stuck in relearning.",
        "expl_stuck_low": "Few or no stuck cards.",

        # Explanations: new cards
        "expl_newret_none": "Not enough data on new cards.",
        "expl_newret_low": "New cards are hard to memorize — more than half get forgotten.",
        "expl_newret_mid": "New cards are being absorbed at an average level.",
        "expl_newret_good": "New cards are being absorbed well.",
        "expl_newret_high": "New cards are being absorbed excellently.",

        # Explanations: unstable share
        "expl_lowstab_none": "Not enough data on unstable cards.",
        "expl_lowstab_high": "Many cards have low stability — the material hasn't consolidated yet.",
        "expl_lowstab_mid": "A moderate share of unstable cards.",
        "expl_lowstab_low": "Few unstable cards — the material is consolidating well.",

        # Chart captions
        "cap_true_retention": "The chart shows daily recall, in percent.",
        "cap_new_card_retention": "The scale shows the share of new cards successfully recalled (0–100%). Calculated over the last 30 days — independent of the analysis period.",
        "cap_avg_difficulty": "The scale shows the current difficulty level from 0 to 10.",
        "cap_avg_stability": "The scale shows card stability — the number of days before recall drops to 90%.",
        "cap_low_stability_ratio": "Shows what share of cards are still unstable (they can be forgotten quickly).",
        "cap_actual_vs_predicted": "Comparison of review counts: expected and actually completed.",
        "cap_avg_time_growth": "Comparison of average time per card: before and now (in seconds).",
        "cap_consistency": "The chart shows the number of cards completed on each day.",
        "cap_relearning_stuck": "The diagram shows how many of the cards completed today got stuck and how many are fine.",
        "donut_stuck": "Stuck",
        "donut_ok": "Fine",
        "chart_empty_note": "No cards completed yet today for this chart.",

        # Bar pair labels
        "lbl_expected": "Expected",
        "lbl_actual": "Actual",
        "lbl_before": "Before",
        "lbl_now": "Now",

        # Note and Summary tab
        "stats_note": "Below are metrics for the last {period} days. They may differ from Anki's overall statistics.",
        "summary_subtitle": "Statistics score for the last {period} days",
        "sum_comment_1": "Things are tough for you right now — the material isn't sticking well, and you can feel it. That's okay, it happens to everyone. It's worth slowing down and easing the load until you catch up.",
        "sum_comment_2": "Your results are below your usual — some of the material is evaporating faster than you'd like. It's worth easing off the pace a bit and spending time reviewing what you've already covered.",
        "sum_comment_3": "You're holding up fine overall — nothing critical, but no big safety margin either. There's room to grow if you give your reviews a bit more attention.",
        "sum_comment_4": "You're doing well — the material is consolidating confidently, with almost no slip-ups. Keep it up.",
        "sum_comment_5": "An excellent result — you're locking in the material very confidently and steadily. You could even speed up a little if you want to move faster.",
        "sum_cmp_better": "Clearly better than last time (was {prev}/10)",
        "sum_cmp_worse": "Dropped a bit compared to last time (was {prev}/10)",
        "sum_cmp_same": "Holding at about the same level (was {prev}/10)",
        "rec_title": "What can be improved",
        "rec_empty": "No obvious weak spots — you can simply keep doing what you're doing.",
        "rec_true_retention": "Give your reviews a bit more attention — recall is lower than you'd want right now.",
        "rec_new_card_retention": "Don't rush to add lots of new cards at once — give the fresh material time to settle.",
        "rec_avg_difficulty": "Many cards are genuinely hard — try slowing down on adding new ones for a while.",
        "rec_avg_stability": "Some material is still unstable in memory — it's worth revisiting it through review.",
        "rec_low_stability_ratio": "A noticeable share of cards hasn't consolidated yet — they need more time and attention.",
        "rec_actual_vs_predicted": "Your workload is noticeably higher than intended — worth revisiting the new-card limit.",
        "rec_avg_time_growth": "Cards are taking more time than before — maybe take a break or slow down the pace.",
        "rec_consistency": "Your sessions are irregular — try studying at a roughly steady rhythm; it helps retention.",
        "rec_relearning_stuck": "Quite a few cards are stuck in relearning — worth working on those specifically.",

        # Weekdays
        "day_1": "Mon",
        "day_2": "Tue",
        "day_3": "Wed",
        "day_4": "Thu",
        "day_5": "Fri",
        "day_6": "Sat",
        "day_7": "Sun",

        # Mascot dialogs
        "dlg_days_title": "Anker — weekdays",
        "pv_increase_msg": "You're handling the “{deck_name}” deck with confidence — you could pick up the pace a little and add some new cards.",
        "pv_increase_yes": "Yes, let's increase",
        "pv_increase_no": "Keep it as is for now",
        "pv_decrease_msg": "Reviews of “{deck_name}” have been harder for you lately. It makes sense to lower the number of new cards for a while to consolidate what you've already learned.",
        "pv_decrease_yes": "Yes, let's lower it",
        "pv_decrease_no": "No, I can handle it",
        "pv_stable_msg": "You've been consolidating the material in “{deck_name}” consistently well — and not just for one week. Don't get too relaxed, but the pace is great!",
        "pv_stable_btn": "Thanks!",
        "pv_neutral_msg": "Everything's steady with “{deck_name}” — keep going at your own pace.",
        "pv_neutral_btn": "Okay",
        "an_msg": "“{deck_name}” is clearly harder than usual for you today. What happened?",
        "an_lazy": "Feeling lazy / don't want to",
        "an_busy": "Busy today",
        "an_dismiss": "It'll pass",
        "lazy_msg": "It happens to everyone, don't worry. Let's set up a temporary light mode for “{deck_name}” — I'll lower the number of new cards for a while, and then everything goes back to normal.",
        "lazy_3": "Light mode for 3 days",
        "lazy_5": "Light mode for 5 days",
        "lazy_7": "Light mode for 7 days",
        "lazy_no": "No need, I'm fine",
        "busy_msg": "I understand, those days happen. Want me to set up weekdays without new cards for “{deck_name}”?",
        "busy_setup": "Set up weekdays",
        "busy_skip": "Not today",
        "days_msg": "On which days do you usually have no time for new cards in “{deck_name}”? Mark them — I'll adapt.",

        # Deck selector
        "ds_title": "Anker — deck selection",
        "ds_warning": "⚠ Some decks are nested inside each other — this will double-count cards. Keep only the parent deck.",
        "ds_search": "Search decks…",
        "ds_all": "Select all",
        "ds_none": "Deselect all",
        "ds_conflict": "You can't select a parent and a child deck at the same time. Keep only the parent deck.",

        # Menu and service messages
        "menu_settings": "Settings…",
        "menu_decks": "Select decks…",
        "menu_force": "Run analysis now (test)",
        "menu_mascot": "Show mascot (test)",
        "menu_reset": "Reset state",
        "lang_label": "Choose the interface language:",
        "lang_set_ru": "Anker: язык интерфейса — русский.",
        "lang_set_en": "Anker: interface language — English.",
        "set_title": "Anker — settings",
        "set_label": "Analysis period (days):\nDetermines how often Anker checks your statistics\nand the time span they're calculated over.",
        "set_saved": "Anker: analysis period — {period} d",
        "tt_decks": "Anker: decks selected — {n}",
        "msg_no_deck": "No deck selected. Choose at least one deck for the test in the Anker settings: Anker → Select decks…",
        "msg_history": "Deck “{deck_name}”: not enough history — need at least {min_days} days, currently {actual_days}.\n\nTip: for a quick check you can temporarily lower min_history_days in the addon config (for example, to 1).",
        "tt_light": "Anker: light mode for “{deck_name}” for {days} days",
        "tt_limit_up": "Anker: limit increased, new ≈ {target}",
        "tt_limit_down": "Anker: limit decreased, new ≈ {target}",
        "tt_limit_err": "Anker: failed to change the deck limit: {err}",
        "tt_reset": "Anker: state reset, deck selection cleared.",
        "msg_save_err": "Failed to save settings: {err}",
        "tt_test": "Anker test action: {action}",
        "test_reason": "Test run.",
    },
}


# ── Чтение языка из config.json (с кэшем по mtime) ────────────────────────

_cached_lang = LANG_RU
_cached_mtime = None


def get_lang() -> str:
    """Текущий язык интерфейса: 'ru' или 'en' (по умолчанию 'ru')."""
    global _cached_lang, _cached_mtime
    try:
        mtime = os.path.getmtime(_CONFIG_PATH)
        if _cached_mtime is None or mtime != _cached_mtime:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            lang = cfg.get("language", LANG_RU)
            _cached_lang = lang if lang in (LANG_RU, LANG_EN) else LANG_RU
            _cached_mtime = mtime
    except Exception:
        _cached_lang = LANG_RU
    return _cached_lang


def t(key: str, **kwargs) -> str:
    """Строка на текущем языке; {kwargs} подставляются через format."""
    lang = get_lang()
    text = STRINGS.get(lang, {}).get(key)
    if text is None:
        text = STRINGS[LANG_RU].get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

# ── Установка языка (для LanguageDialog) ───────────────────────────────────

def set_lang(lang: str) -> None:
    """Принудительно устанавливает язык (для диалога выбора)."""
    global _cached_lang
    _cached_lang = lang if lang in (LANG_RU, LANG_EN) else LANG_RU