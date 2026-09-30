{% load ui_modules %}{% comment %} The application script: ES modules resolved through an import map.
   The map must come before the first module script. A browser without import
   maps (before Chrome 89, Firefox 108, Safari 16.4) cannot start the panel, so
   it is told so instead of being left with a page that silently does nothing. {% endcomment %}
{% dolphin_import_map %}
<script type="module" src="{% dolphin_entry_url %}"></script>
<script>
    if (!(window.HTMLScriptElement && HTMLScriptElement.supports && HTMLScriptElement.supports("importmap"))) {
        document.addEventListener("DOMContentLoaded", function () {
            var note = document.createElement("div");
            note.setAttribute("role", "alert");
            note.style.cssText = "padding:12px 16px;background:#fff3cd;color:#664d03;text-align:center;font-family:sans-serif";
            note.textContent = "این مرورگر قدیمی است و پنل کامل کار نمی‌کند. لطفاً مرورگر خود را به‌روز کنید.";
            document.body.prepend(note);
        });
    }
</script>
