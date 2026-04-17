import GramAddict
from GramAddict.core.device_facade import DeviceFacade, Mode, SleepTime

_original_set_text = DeviceFacade.View.set_text


def _patched_set_text(self, text, mode=Mode.TYPE):
    if "\n" in text:
        try:
            self.deviceV2.clipboard = text
            self.click(sleep=SleepTime.SHORT)
            self.deviceV2.shell("input keyevent 279")
            DeviceFacade.sleep_mode(SleepTime.SHORT)
            return
        except Exception:
            pass
    _original_set_text(self, text, mode)


DeviceFacade.View.set_text = _patched_set_text

GramAddict.run()
