# -*- coding: utf-8 -*-
"""
الباحث الحديثي - برنامج للبحث في الأحاديث النبوية الشريفة
"""

VERSION = "1.0.0"
GITHUB_REPO = "ahmad74444/hadith-search"

import wx
import threading
import urllib.request
import urllib.parse
import json
import webbrowser
import re
import ssl


API_BASE = "https://hadeethenc.com/api/v1"
SEARCH_URL = f"{API_BASE}/hadeeths/search/"
ONE_URL = f"{API_BASE}/hadeeths/one/"
LANGUAGE = "ar"
DETAIL_TIMEOUT = 8  # مهلة قصيرة لجلب التفاصيل

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def do_request(url, timeout=30):
    req = urllib.request.Request(url)
    req.add_header('Accept', 'application/json')
    req.add_header('User-Agent', 'HadithSearchApp/1.0')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except (ssl.SSLError, urllib.error.URLError):
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as r:
            return json.loads(r.read().decode('utf-8'))


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    for o, n in [('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"')]:
        text = text.replace(o, n)
    return text.strip()


def build_list_label(item):
    """بناء نص القائمة — كل المحتوى المتوفر في سطر واحد"""
    segs = []
    title = strip_html(item.get('title', ''))
    if title:
        segs.append(f"العنوان: {title}")

    # نص الحديث (يأتي بأسماء مختلفة حسب المصدر)
    hadith = strip_html(
        item.get('hadeeth', '') or item.get('hadith_text', '')
    )
    if hadith:
        segs.append(f"الحديث: {hadith.replace(chr(10), ' ').replace(chr(13), '')}")

    for key, label in [('attribution', 'الراوي'), ('grade', 'الدرجة')]:
        v = strip_html(item.get(key, ''))
        if v:
            segs.append(f"{label}: {v}")

    ref = strip_html(item.get('reference', ''))
    if ref:
        segs.append(f"المصدر: {ref.replace(chr(10), ' ').replace(chr(13), '')}")

    exp = strip_html(item.get('explanation', ''))
    if exp:
        segs.append(f"الشرح: {exp.replace(chr(10), ' ').replace(chr(13), '')}")

    wm = strip_html(item.get('words_meanings', ''))
    if wm:
        segs.append(f"معاني الكلمات: {wm.replace(chr(10), ' ').replace(chr(13), '')}")

    hints = item.get('hints', '')
    if hints:
        if isinstance(hints, list):
            ht = ' '.join(strip_html(h) for h in hints if h)
        else:
            ht = strip_html(hints)
        if ht:
            segs.append(f"ما يستفاد من الحديث: {ht.replace(chr(10), ' ').replace(chr(13), '')}")

    return ". ".join(segs) if segs else "(بدون عنوان)"


def build_detail_text(item):
    """بناء نص مربع التفاصيل — متعدد الأسطر"""
    parts = []
    title = strip_html(item.get('title', ''))
    if title:
        parts.append(f"العنوان: {title}")
        parts.append("")

    hadith = strip_html(item.get('hadeeth', '') or item.get('hadith_text', ''))
    if hadith:
        parts.append("نص الحديث:")
        parts.append(hadith)
        parts.append("")

    for key, label in [('attribution', 'الراوي'), ('grade', 'الدرجة'), ('reference', 'المصدر')]:
        v = strip_html(item.get(key, ''))
        if v:
            parts.append(f"{label}: {v}")
    parts.append("")

    exp = strip_html(item.get('explanation', ''))
    if exp:
        parts.append("الشرح:")
        parts.append(exp)
        parts.append("")

    wm = strip_html(item.get('words_meanings', ''))
    if wm:
        parts.append("معاني الكلمات:")
        parts.append(wm)
        parts.append("")

    hints = item.get('hints', '')
    if hints:
        if isinstance(hints, list):
            ht = '\n'.join(f"- {strip_html(h)}" for h in hints if h)
        else:
            ht = strip_html(hints)
        if ht:
            parts.append("ما يستفاد من الحديث:")
            parts.append(ht)

    return '\n'.join(parts)


class HadithSearchFrame(wx.Frame):

    def __init__(self):
        super().__init__(
            None,
            title="الباحث الحديثي - موسوعة الأحاديث النبوية",
            size=(800, 600),
        )
        self.all_items = []     # كل النتائج (بيانات البحث + تفاصيل إن وُجدت)
        self.detail_cache = {}  # id -> تفاصيل كاملة
        self.is_searching = False
        self._last_shown_idx = -1  # آخر عنصر عُرضت تفاصيله

        self._build_ui()
        self.Centre()
        self.Show()
        self.search_input.SetFocus()

    def _build_ui(self):
        # ──── شريط القوائم ────
        menu_bar = wx.MenuBar()
        help_menu = wx.Menu()
        about_id = help_menu.Append(wx.ID_ABOUT, "حول البرنامج\tF1").GetId()
        update_id = help_menu.Append(wx.ID_ANY, "البحث عن التحديثات").GetId()
        menu_bar.Append(help_menu, "مساعدة")
        self.SetMenuBar(menu_bar)
        self.Bind(wx.EVT_MENU, self.on_about, id=about_id)
        self.Bind(wx.EVT_MENU, self.on_check_update, id=update_id)

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # بحث
        hs = wx.BoxSizer(wx.HORIZONTAL)
        hs.Add(wx.StaticText(panel, label="بحث عن حديث:"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.search_input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, name="مربع البحث")
        hs.Add(self.search_input, 1, wx.ALL | wx.EXPAND, 5)
        self.search_btn = wx.Button(panel, label="بحث")
        hs.Add(self.search_btn, 0, wx.ALL, 5)
        sizer.Add(hs, 0, wx.EXPAND)

        # حالة
        self.status_label = wx.StaticText(
            panel, label="مرحباً بك في الباحث الحديثي. اكتب كلمة البحث واضغط Enter."
        )
        sizer.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 5)

        # نتائج
        self.results_label = wx.StaticText(panel, label="نتائج البحث:")
        sizer.Add(self.results_label, 0, wx.LEFT | wx.TOP, 5)
        self.results_list = wx.ListBox(panel, style=wx.LB_SINGLE, name="قائمة نتائج البحث")
        sizer.Add(self.results_list, 1, wx.ALL | wx.EXPAND, 5)

        # تفاصيل
        sizer.Add(wx.StaticText(panel, label="تفاصيل الحديث المحدد:"), 0, wx.LEFT | wx.TOP, 5)
        self.detail_text = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, name="تفاصيل الحديث"
        )
        sizer.Add(self.detail_text, 1, wx.ALL | wx.EXPAND, 5)

        panel.SetSizer(sizer)

        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        self.results_list.Bind(wx.EVT_LISTBOX, self.on_result_selected)
        self.results_list.Bind(wx.EVT_KEY_UP, self.on_list_key)
        self.results_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)

    def on_list_key(self, event):
        """معالجة أحداث لوحة المفاتيح على القائمة لدعم NVDA"""
        key = event.GetKeyCode()
        if key in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME, wx.WXK_END,
                   wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
            self._update_detail_for_selection()
        event.Skip()

    # ────────── قائمة المساعدة ──────────

    def on_about(self, event):
        """عرض نافذة حول البرنامج"""
        msg = (
            "الباحث الحديثي\n"
            f"الإصدار: {VERSION}\n\n"
            "برنامج للبحث في الأحاديث النبوية الشريفة\n"
            "مع شرحها وتخريجها ودرجتها.\n\n"
            "مصدر البيانات:\n"
            "موسوعة الأحاديث النبوية المترجمة\n"
            "https://hadeethenc.com\n\n"
            "فكرة وتصميم: أحمد الغنيم"
        )
        dlg = wx.MessageDialog(self, msg, "حول البرنامج", wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def on_check_update(self, event):
        """البحث عن تحديثات جديدة عبر GitHub"""
        self.status_label.SetLabel("جارٍ البحث عن التحديثات...")
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def _check_update_worker(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url)
            req.add_header('Accept', 'application/vnd.github.v3+json')
            req.add_header('User-Agent', 'HadithSearchApp/1.0')
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode('utf-8'))
            except (ssl.SSLError, urllib.error.URLError):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
                    data = json.loads(r.read().decode('utf-8'))

            latest = data.get('tag_name', '').lstrip('v')
            html_url = data.get('html_url', '')
            body = data.get('body', '')

            if latest and latest != VERSION:
                wx.CallAfter(self._update_available, latest, html_url, body)
            else:
                wx.CallAfter(self._no_update)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                wx.CallAfter(self._no_update)
            else:
                wx.CallAfter(self._update_error, str(e))
        except Exception as e:
            wx.CallAfter(self._update_error, str(e))

    def _update_available(self, version, url, body):
        self.status_label.SetLabel(f"يوجد إصدار جديد: {version}")
        msg = f"يوجد إصدار جديد: {version}\n\n"
        if body:
            msg += f"{body}\n\n"
        msg += "هل تريد فتح صفحة التحميل؟"
        dlg = wx.MessageDialog(self, msg, "تحديث متوفر", wx.YES_NO | wx.ICON_INFORMATION)
        if dlg.ShowModal() == wx.ID_YES and url:
            webbrowser.open(url)
        dlg.Destroy()

    def _no_update(self):
        self.status_label.SetLabel("أنت تستخدم أحدث إصدار.")
        wx.MessageBox("أنت تستخدم أحدث إصدار من البرنامج.", "لا توجد تحديثات", wx.OK | wx.ICON_INFORMATION)

    def _update_error(self, error):
        self.status_label.SetLabel("تعذر البحث عن التحديثات.")
        wx.MessageBox(f"تعذر البحث عن التحديثات:\n{error}", "خطأ", wx.OK | wx.ICON_ERROR)

    # ────────── قائمة السياق (كليك يمين / زر التطبيقات) ──────────

    def on_context_menu(self, event):
        """عرض قائمة السياق عند الضغط بزر الفأرة الأيمن أو زر التطبيقات"""
        idx = self.results_list.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self.all_items):
            return

        menu = wx.Menu()
        open_item = menu.Append(wx.ID_ANY, "فتح في الموقع")
        self.Bind(wx.EVT_MENU, lambda evt: self._open_in_browser(idx), open_item)
        self.results_list.PopupMenu(menu)
        menu.Destroy()

    def _open_in_browser(self, idx):
        """فتح الحديث المحدد في المتصفح"""
        item = self.all_items[idx]
        hid = item.get('id', '')
        if hid:
            url = f"https://hadeethenc.com/ar/browse/hadith/{hid}"
            webbrowser.open(url)

    # ────────── البحث ──────────

    def on_search(self, event):
        phrase = self.search_input.GetValue().strip()
        if not phrase or self.is_searching:
            return
        self.all_items = []
        self.detail_cache = {}
        self._last_shown_idx = -1
        self.results_list.Clear()
        self.detail_text.SetValue("")
        self.results_label.SetLabel("نتائج البحث:")
        self.is_searching = True
        self.search_btn.Enable(False)
        self.status_label.SetLabel("جارٍ البحث... الرجاء الانتظار.")
        threading.Thread(target=self._do_search, args=(phrase,), daemon=True).start()

    def _do_search(self, phrase):
        try:
            params = urllib.parse.urlencode({'phrase': phrase, 'language': LANGUAGE})
            data = do_request(f"{SEARCH_URL}?{params}")
            items = data if isinstance(data, list) else data.get('data', []) if isinstance(data, dict) else []
            wx.CallAfter(self._search_done, items, None)
        except Exception as e:
            wx.CallAfter(self._search_done, None, str(e))

    def _search_done(self, items, error):
        self.is_searching = False
        self.search_btn.Enable(True)
        if error:
            self.status_label.SetLabel(f"خطأ: {error}")
            return
        if not items:
            self.status_label.SetLabel("لا توجد نتائج.")
            self.results_label.SetLabel("نتائج البحث: 0 نتيجة")
            return

        self.all_items = items
        total = len(items)
        for item in items:
            self.results_list.Append(build_list_label(item))

        self.results_label.SetLabel(f"نتائج البحث: {total} نتيجة")
        self.status_label.SetLabel(f"تم العثور على {total} نتيجة. اختر حديثاً لعرض تفاصيله.")
        self.results_list.SetSelection(0)
        self.results_list.SetFocus()
        # عرض البيانات المتوفرة فوراً + محاولة جلب التفاصيل
        self._show_and_fetch(0)

    # ────────── عرض + جلب التفاصيل ──────────

    def on_result_selected(self, event):
        self._update_detail_for_selection()

    def _update_detail_for_selection(self):
        """تحديث التفاصيل بناء على العنصر المحدد حالياً"""
        idx = self.results_list.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self.all_items):
            return
        if idx == self._last_shown_idx:
            return  # لا حاجة لإعادة العرض
        self._last_shown_idx = idx
        self._show_and_fetch(idx)

    def _show_and_fetch(self, idx):
        """عرض ما هو متاح فوراً ثم محاولة جلب التفاصيل"""
        item = self.all_items[idx]
        hid = str(item.get('id', ''))

        # إذا التفاصيل محملة مسبقاً
        if hid in self.detail_cache:
            merged = self.detail_cache[hid]
            self.detail_text.SetValue(build_detail_text(merged))
            return

        # عرض ما هو متاح الآن فوراً
        self.detail_text.SetValue(build_detail_text(item))

        # محاولة جلب التفاصيل الكاملة في الخلفية
        if hid:
            threading.Thread(
                target=self._try_fetch_detail, args=(idx, hid), daemon=True
            ).start()

    def _try_fetch_detail(self, idx, hid):
        try:
            params = urllib.parse.urlencode({'id': hid, 'language': LANGUAGE})
            detail = do_request(f"{ONE_URL}?{params}", timeout=DETAIL_TIMEOUT)
            wx.CallAfter(self._detail_arrived, idx, hid, detail)
        except Exception:
            pass  # التفاصيل الإضافية اختيارية — نبقى على ما عُرض

    def _detail_arrived(self, idx, hid, detail):
        # حفظ في الذاكرة المؤقتة
        self.detail_cache[hid] = detail

        # دمج التفاصيل مع بيانات البحث وحفظها
        if idx < len(self.all_items):
            self.all_items[idx] = {**self.all_items[idx], **detail}
            # تحديث نص القائمة ليشمل التفاصيل الكاملة
            current_sel = self.results_list.GetSelection()
            self.results_list.SetString(idx, build_list_label(self.all_items[idx]))
            # إعادة التحديد لأن SetString قد يفقده
            if current_sel != wx.NOT_FOUND:
                self.results_list.SetSelection(current_sel)

        # تحديث مربع التفاصيل إن كان المستخدم لا يزال على نفس العنصر
        if self.results_list.GetSelection() == idx:
            self.detail_text.SetValue(build_detail_text(detail))


if __name__ == "__main__":
    app = wx.App()
    app.SetAppName("الباحث الحديثي")
    HadithSearchFrame()
    app.MainLoop()
