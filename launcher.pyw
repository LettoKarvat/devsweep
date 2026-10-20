import sys
from devsweep.app import App, main

if sys.argv[1:] == ["--smoke-test"]:
    app = App()
    app.withdraw()
    app.update_idletasks()
    assert not app.checked
    assert str(app.trash_button.cget("state")) == "disabled"
    app.destroy()
else:
    main()
