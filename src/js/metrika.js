/* Цели Яндекс.Метрики - все в одном месте.
   Номер счётчика задаётся в config.json (metrika_id), код счётчика вставляет build.py.
   В интерфейсе Метрики: Цели -> JavaScript-событие -> идентификатор из правого столбца. */
(function () {
  var GOALS = {
    call: 'click_phone',         // клик по номеру телефона (шапка, карточка, нижняя панель)
    whatsapp: 'click_whatsapp',  // переход в WhatsApp
    telegram: 'click_telegram',  // переход в Telegram
    lead: 'form_lead',           // отправлена форма «Оставить заявку»
    bron: 'form_bron',           // отправлена бронь комплекта
    vykup: 'form_vykup'          // отправлена заявка на выкуп
  };

  window.pkGoal = function (name, params) {
    var id = GOALS[name] || name;
    var counter = (window.PK || {}).metrika;
    if (counter && typeof window.ym === 'function') {
      window.ym(counter, 'reachGoal', id, params || {});
    } else {
      console.info('[Метрика, демо] reachGoal', id, params || {});
    }
    (window.pkGoalLog = window.pkGoalLog || []).push({ goal: id, params: params || {}, t: Date.now() });
  };
})();
