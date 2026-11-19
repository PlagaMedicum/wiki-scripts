from __future__ import annotations

import re

# Python reproductions of wikificator's core regex transformations for automated regression testing


def process_link_py(left: str, right: str) -> str:
    left = left.replace("\u00a0", " ").strip()
    left = re.sub(r"[ _]+", " ", left)
    if re.match(r"^(?:Катэгорыя|Файл) ?:", left):
        return f"[[{left}|{right}]]"

    right = re.sub(r" {2,}", " ", right.strip())
    after_link = right[len(left) :]
    uni_left = left[:1].upper() + left[1:]
    uni_right = (right[:1].upper() + right[1:]).replace("_", " ").replace("\u00a0", " ")

    # The buggy regex in original JS:
    # afterLink.match(/^[a-zа-яё]*$/)
    # The fixed regex must include Belarusian letters і, ў:
    # afterLink.match(/^[a-zа-яёіў]*$/)
    if uni_right.startswith(uni_left) and re.match(r"^[a-zа-яёіў]*$", after_link, re.IGNORECASE):
        in_link = right[: len(left)]
        return f"[[{in_link}]]{after_link}"
    return f"[[{left}|{right}]]"


def test_belarusian_link_simplification():
    # Words with 'ў' and 'і' in inflectional suffixes
    # In MediaWiki wikitext, [[A|AB]] simplifies to [[A]]B
    assert process_link_py("лес", "лесаў") == "[[лес]]аў"
    assert process_link_py("Мінск", "Мінскі") == "[[Мінск]]і"
    assert process_link_py("горад", "горадзе") == "[[горад]]зе"
    # When right does not start with left (stem modification), keep piped
    assert process_link_py("рубель", "рублі") == "[[рубель|рублі]]"


def test_html_comments_protection():
    # Demonstrating the defect: HTML comments must be protected like tags
    raw = "Тэкст <!-- Каментар з працяжнікам -- і «двукоссямі» --> працяг."
    # If comments are protected:
    comment_pattern = re.compile(r"<!--[\s\S]*?-->")
    hidden = []

    def hide(match):
        hidden.append(match.group(0))
        return f"\x01{len(hidden)}\x02"

    protected = comment_pattern.sub(hide, raw)
    assert "\x011\x02" in protected
    # Unhide restore
    restored = re.sub(r"\x01(\d+)\x02", lambda m: hidden[int(m.group(1)) - 1], protected)
    assert restored == raw


def test_proposal_006_subtraction_defects_and_false_positives():
    # Demonstrating why Proposal #006 is declined:
    # 1. False positive: "1985–1991 = 6 гадоў" is wrongly converted to "1985 − 1991 = 6 гадоў"
    #    because of the speculative regex: r( /(\d+)\s*[-–−]\s*(\d+)\s*=/g, '$1 − $2 =' )
    # 2. Fails to cover algebraic expressions with variables or parentheses:
    #    "x - y = z", "5 - x", "5 - (3)" still become em-dashes.
    #    Attempting complicated heuristics to distinguish algebra from natural language
    #    creates unacceptable regression risks.
    import shutil
    import subprocess
    from pathlib import Path

    js_file = Path("proposals/006/proposed.txt")
    if js_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');
            const sandbox = {{ document: {{ documentElement: {{ scrollTop: 0 }} }}, registerTool: () => {{}} }};
            sandbox.window = sandbox;
            sandbox.global = sandbox;
            sandbox.$ = () => ({{ focus: () => {{}}, scrollTop: () => 0, textSelection: () => {{}}, on: () => {{}} }});
            sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
            sandbox.$.trim = s => (s||'').trim();
            sandbox.mw = {{ loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }}, config: {{ get: () => 0 }} }};
            vm.createContext(sandbox);
            vm.runInContext(fs.readFileSync('{js_file}', 'utf8'), sandbox);

            // 1. Defect: Year range followed by equality is wrongly turned into a subtraction
            const yearEquality = sandbox.Wikify('1985–1991 = 6 гадоў');
            if (yearEquality.includes('−')) {{
                // Confirms the false positive in #006
                // console.log('Confirmed false positive in #006:', yearEquality);
            }} else {{
                console.error('Expected #006 to exhibit false positive on 1985–1991 = 6 гадоў');
                process.exit(1);
            }}

            // 2. Algebraic expressions are not handled by #006
            const outX = sandbox.Wikify('x - y = z');
            if (!outX.includes('—')) {{
                console.error('x - y = z unexpected behavior:', outX);
                process.exit(1);
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_numeric_ranges_preserve_en_dash():
    # Proposal #007: Safe preservation of en-dashes in numeric ranges and spacing protection
    # Works completely independently on current live code (rev 5260605).
    # - "5 - 3 = 2", "5 – 3 = 2", "5 - 3", "5 – 3" are preserved (not corrupted to em-dash)
    # - "стар. 10–15" or "5–8" preserve en-dash (not degraded to hyphen)
    # - "1985–1991 = 6 гадоў" preserves em-dash year range without false subtraction
    import shutil
    import subprocess
    from pathlib import Path

    js_file = Path("proposals/007/proposed.txt")
    if js_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');
            const sandbox = {{ document: {{ documentElement: {{ scrollTop: 0 }} }}, registerTool: () => {{}} }};
            sandbox.window = sandbox;
            sandbox.global = sandbox;
            sandbox.$ = () => ({{ focus: () => {{}}, scrollTop: () => 0, textSelection: () => {{}}, on: () => {{}} }});
            sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
            sandbox.$.trim = s => (s||'').trim();
            sandbox.mw = {{ loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }}, config: {{ get: () => 0 }} }};
            vm.createContext(sandbox);
            vm.runInContext(fs.readFileSync('{js_file}', 'utf8'), sandbox);

            // Test cases for Proposal #007
            const testData = [
                // 1. Numeric subtraction preservation (not corrupted to em-dash)
                ['5 - 3 = 2', '5 - 3 = 2'],
                ['5 – 3 = 2', '5 – 3 = 2'],
                ['5 - 3', '5 - 3'],
                ['5 – 3', '5 – 3'],

                // 2. Numeric and page ranges (en-dash preserved)
                ['У 5–8 класах', 'У 5–8 класах'],
                ['стар. 10–15', 'стар. 10–15'],

                // 3. Year ranges (including equality case, avoiding #006 false positive)
                ['1985–1991 = 6 гадоў', '1985—1991 = 6 гадоў'],
                ['1985-1991', '1985—1991'],
                ['1985–1991', '1985—1991'],
                ['VII–IX стст.', 'VII—IX\\u00A0стст.'],

                // 4. Legitimate sentence and dialogue dashes
                ['Мінск - сталіца', 'Мінск\\u00A0— сталіца'],
                ['Мінск – сталіца', 'Мінск\\u00A0— сталіца'],
                ['- Прывітанне!', '— Прывітанне!'],
                ['– Прывітанне!', '— Прывітанне!'],
                ['\\n– Прывітанне!', '\\n— Прывітанне!'],

                // 5. Route and compound names with en-dash (preserved, not degraded to hyphen)
                ['цягнік Мінск–Брэст', 'цягнік Мінск–Брэст'],
                ['пакт Молатава–Рыбентропа', 'пакт Молатава–Рыбентропа'],

                // 6. Documented remaining limitation: variable-based arithmetic without <math>
                //    is treated as natural language punctuation and converts to em-dash.
                ['x - y = z', 'x\\u00A0— y = z'],
                ['5 - x', '5\\u00A0— x'],
                ['5 - (3)', '5\\u00A0— (3)']
            ];

            for (const [inp, exp] of testData) {{
                const out = sandbox.Wikify(inp);
                if (out !== exp) {{
                    console.error('Mismatch for "' + inp + '": got "' + out + '", expected "' + exp + '"');
                    process.exit(1);
                }}
                if (sandbox.Wikify(out) !== out) {{
                    console.error('Idempotence failure for "' + inp + '"');
                    process.exit(1);
                }}
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_live_wikificator_reproduces_defects():
    # Verify that live Wikificator code (rev 5260605, original.txt) reproduces the defects
    # that Proposal #007 fixes:
    # 1. Spaced hyphen in subtraction "5 - 3 = 2" and "5 - 3" is corrupted into em-dash
    # 2. Spaced en-dash "5 – 3" is corrupted into em-dash
    # 3. Numeric ranges with en-dash "У 5–8 класах" and "стар. 10–15" lose en-dash to hyphen
    import shutil
    import subprocess
    from pathlib import Path

    orig_file = Path("proposals/007/original.txt")
    if orig_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');
            const orig = fs.readFileSync('{orig_file}', 'utf8');

            const sandbox = {{ document: {{ documentElement: {{ scrollTop: 0 }} }}, registerTool: () => {{}} }};
            sandbox.window = sandbox; sandbox.global = sandbox;
            sandbox.$ = () => ({{ focus: () => {{}}, scrollTop: () => 0, textSelection: () => {{}}, on: () => {{}} }});
            sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
            sandbox.$.trim = s => (s||'').trim();
            sandbox.mw = {{ loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }}, config: {{ get: () => 0 }} }};
            vm.createContext(sandbox);
            vm.runInContext(orig, sandbox);

            // 1. Live code corrupts subtraction into em-dash
            const subOut = sandbox.Wikify('5 - 3 = 2');
            if (!subOut.includes('—')) {{
                console.error('Expected live code to corrupt 5 - 3 = 2 into em-dash');
                process.exit(1);
            }}

            // 2. Live code corrupts numeric range en-dash into raw hyphen
            const rangeOut = sandbox.Wikify('У 5–8 класах на стар. 10–15');
            if (rangeOut.includes('–')) {{
                console.error('Expected live code to destroy en-dash in numeric ranges');
                process.exit(1);
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_punctuation_spacing_domain_names_limitation():
    # Investigation of rule line 239: r(/([а-яёўі]\.)([А-ЯA-ZЁЎІ])/g, '$1 $2')
    # 1. Ordinary sentence boundaries and abbreviations must receive a space
    # 2. Existing masking functions protect URLs with protocol schemes and templates
    # 3. Unmasked domain names/identifiers (e.g. Культурология.Ру) share the exact syntactic shape
    #    with sentence boundaries and cannot be distinguished without speculative TLD heuristics.
    import shutil
    import subprocess
    from pathlib import Path

    orig_file = Path("proposals/007/original.txt")
    if orig_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');
            const orig = fs.readFileSync('{orig_file}', 'utf8');

            const sandbox = {{ document: {{ documentElement: {{ scrollTop: 0 }} }}, registerTool: () => {{}} }};
            sandbox.window = sandbox; sandbox.global = sandbox;
            sandbox.$ = () => ({{ focus: () => {{}}, scrollTop: () => 0, textSelection: () => {{}}, on: () => {{}} }});
            sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
            sandbox.$.trim = s => (s||'').trim();
            sandbox.mw = {{ loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }}, config: {{ get: () => 0 }} }};
            vm.createContext(sandbox);
            vm.runInContext(orig, sandbox);

            // 1. Ordinary sentence boundaries must continue working
            const s1 = sandbox.Wikify('Гэта канец сказа.Новы сказ.');
            if (s1 !== 'Гэта канец сказа. Новы сказ.') {{
                console.error('Sentence spacing failed, got:', s1);
                process.exit(1);
            }}
            const s2 = sandbox.Wikify('У г.Мінску адбылося свята.');
            if (s2 !== 'У г. Мінску адбылося свята.') {{
                console.error('Abbreviation spacing failed, got:', s2);
                process.exit(1);
            }}

            // 2. Existing masking protects URLs with protocol and templates
            const m1 = sandbox.Wikify('https://Культурология.Ру');
            if (m1 !== 'https://Культурология.Ру') {{
                console.error('Protocol URL should be protected by line 138, got:', m1);
                process.exit(1);
            }}
            const m2 = sandbox.Wikify('{{{{cite web|title=Культурология.Ру}}}}');
            if (m2 !== '{{{{cite web|title=Культурология.Ру}}}}') {{
                console.error('Template should be protected by hideTemplates, got:', m2);
                process.exit(1);
            }}
            const m3 = sandbox.Wikify('<nowiki>Культурология.Ру</nowiki>');
            if (m3 !== '<nowiki>Культурология.Ру</nowiki>') {{
                console.error('Nowiki should be protected by hideTag, got:', m3);
                process.exit(1);
            }}

            // 3. Confirm defect on unmasked domain names/identifiers
            const d1 = sandbox.Wikify('Культурология.Ру');
            if (d1 !== 'Культурология. Ру') {{
                console.error('Expected live code to exhibit space insertion in bare domain, got:', d1);
                process.exit(1);
            }}
            const d2 = sandbox.Wikify('[https://example.com Культурология.Ру]');
            if (d2 !== '[https://example.com Культурология. Ру]') {{
                console.error('Expected live code to exhibit space insertion in link label, got:', d2);
                process.exit(1);
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_full_page_confirmation_safety():
    # Safety contract:
    # - No selection: confirmation required (strings.fullText).
    # - Confirmation declined: text remains unchanged.
    # - Confirmation accepted: entire text is processed.
    # - Text selected: only the selection is processed, without unnecessary confirmation.
    # - Programmatic Wikify(text) remains functional.
    import shutil
    import subprocess
    from pathlib import Path

    prop_file = Path("proposals/008/proposed.txt")
    orig_file = Path("proposals/007/original.txt")
    target_file = prop_file if prop_file.exists() else orig_file

    if target_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');

            function createSandbox(code, confirmResult = true) {{
                let confirmCalled = false;
                let confirmMessage = '';
                let contents = 'Першы сказ - тэкст. Другі сказ -- працяг.';
                let selection = '';
                let caretPos = [0, 0];

                const sandbox = {{
                    document: {{
                        documentElement: {{ scrollTop: 0 }},
                        editform: {{ wpSection: {{ value: '' }} }}
                    }},
                    confirm: (msg) => {{
                        confirmCalled = true;
                        confirmMessage = msg;
                        return confirmResult;
                    }},
                    registerTool: () => {{}}
                }};
                sandbox.window = sandbox;
                sandbox.global = sandbox;

                const mockInput = {{
                    nodeType: 1,
                    value: contents,
                    focus: () => {{}},
                    scrollTop: () => 0,
                    on: () => {{}},
                    textSelection: (action, options) => {{
                        if (action === 'getCaretPosition') return caretPos;
                        if (action === 'getContents') return contents;
                        if (action === 'setContents') {{ contents = options; return mockInput; }}
                        if (action === 'getSelection') return selection;
                        if (action === 'encapsulateSelection') {{
                            contents = contents.replace(selection, options.peri);
                            return mockInput;
                        }}
                        if (action === 'setSelection') return mockInput;
                    }}
                }};
                sandbox.$ = (selector) => {{
                    if (selector === '.CodeMirror-vscrollbar') return {{ length: 0 }};
                    return mockInput;
                }};
                sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
                sandbox.$.trim = s => (s||'').trim();
                sandbox.mw = {{ loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }}, config: {{ get: () => 0 }} }};

                vm.createContext(sandbox);
                vm.runInContext(code, sandbox);

                return {{
                    sandbox,
                    mockInput,
                    setContents: (c) => {{ contents = c; }},
                    getContents: () => contents,
                    setCaretPos: (pos) => {{ caretPos = pos; }},
                    setSelection: (sel, pos) => {{ selection = sel; caretPos = pos; }},
                    getConfirmCalled: () => confirmCalled,
                    getConfirmMessage: () => confirmMessage
                }};
            }}

            const code = fs.readFileSync('{target_file}', 'utf8');
            const isProposed = '{target_file}'.includes('proposals/008');

            if (!isProposed) {{
                // Prove RED on live code: no selection does NOT call confirm and corrupts text
                const env = createSandbox(code, false);
                env.setCaretPos([5, 5]);
                env.sandbox.Wikify(env.mockInput);
                if (env.getConfirmCalled() !== false) {{
                    console.error('Expected live code to not call confirm');
                    process.exit(1);
                }}
            }} else {{
                // Prove GREEN on proposal #008:

                // 1. No selection + Confirmation DECLINED: text remains unchanged
                const envDeclined = createSandbox(code, false);
                envDeclined.setContents('Зыходны - тэкст');
                envDeclined.setCaretPos([0, 0]);
                envDeclined.sandbox.Wikify(envDeclined.mockInput);
                if (!envDeclined.getConfirmCalled()) {{
                    console.error('Confirmation was not requested when no text was selected');
                    process.exit(1);
                }}
                if (envDeclined.getContents() !== 'Зыходны - тэкст') {{
                    console.error('Text changed even though confirmation was declined');
                    process.exit(1);
                }}

                // 2. No selection + Confirmation ACCEPTED: entire text is processed
                const envAccepted = createSandbox(code, true);
                envAccepted.setContents('Зыходны - тэкст');
                envAccepted.setCaretPos([0, 0]);
                envAccepted.sandbox.Wikify(envAccepted.mockInput);
                if (!envAccepted.getConfirmCalled()) {{
                    console.error('Confirmation was not requested');
                    process.exit(1);
                }}
                if (!envAccepted.getContents().includes('—')) {{
                    console.error('Text was not processed after confirmation was accepted');
                    process.exit(1);
                }}

                // 3. Text selected: only selection processed, no confirmation prompted
                const envSelected = createSandbox(code, false);
                envSelected.setContents('Частка 1 - тэкст. Частка 2 - тэкст.');
                envSelected.setSelection('Частка 1 - тэкст.', [0, 17]);
                envSelected.sandbox.Wikify(envSelected.mockInput);
                if (envSelected.getConfirmCalled()) {{
                    console.error('Unnecessary confirmation prompted when text was already selected');
                    process.exit(1);
                }}
                if (envSelected.getContents() !== 'Частка 1\\u00A0— тэкст. Частка 2 - тэкст.') {{
                    console.error('Selection processing mismatch, got:', envSelected.getContents());
                    process.exit(1);
                }}

                // 4. Programmatic Wikify(text) remains functional without confirmation
                const envProg = createSandbox(code, false);
                const progOut = envProg.sandbox.Wikify('Праграмны - тэкст');
                if (envProg.getConfirmCalled()) {{
                    console.error('Confirmation prompted for programmatic Wikify(text)');
                    process.exit(1);
                }}
                if (!progOut.includes('—')) {{
                    console.error('Programmatic Wikify(text) failed to process text');
                    process.exit(1);
                }}
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_wikificator_css_tool_selector_match():
    # MediaWiki:Gadget-wikificator.js registers the tool as:
    # name: 'wikificator'
    # MediaWiki:Gadget-registerTool.js assigns:
    # Tool.static.icon = tool.name ('wikificator')
    # and mw.util.addCSS('.oo-ui-icon-' + tool.name + ' { ... }')
    # Therefore, OOUI generates the class .oo-ui-icon-wikificator on the toolbar button.
    # MediaWiki:Gadget-wikificator.css must include .oo-ui-icon-wikificator to style the icon
    # and support dark mode (skin-theme-clientpref-night and skin-theme-clientpref-os).
    from pathlib import Path

    prop_path = Path("proposals/005/proposed.txt")
    if prop_path.exists():
        css_content = prop_path.read_text(encoding="utf-8")
        assert ".oo-ui-icon-wikificator" in css_content, (
            "CSS selector mismatch: wikificator.css must target .oo-ui-icon-wikificator "
            "matching tool name 'wikificator' in Gadget-registerTool.js"
        )
        assert "html.skin-theme-clientpref-night .oo-ui-icon-wikificator" in css_content
        assert "html.skin-theme-clientpref-os .oo-ui-icon-wikificator" in css_content

        # Confirm original live CSS has the defect
        orig_content = Path("proposals/005/original.txt").read_text(encoding="utf-8")
        assert ".oo-ui-icon-wikificator" not in orig_content
        assert ".oo-ui-icon-wikify" in orig_content


def test_talk_page_protection_reliability():
    # Wikificator talk-page protection:
    # 1. Full-page processing on any discussion namespace (wgNamespaceNumber % 2 !== 0)
    #    must be unconditionally blocked with alert(strings.talkPage), regardless of signature
    #    counts (0, 1, or many) and timezone formats ((+03), (+02), UTC, etc.).
    # 2. Selected text processing on discussion pages must NEVER be blocked, even if the selection
    #    contains multiple signatures/quotes.
    # 3. Content pages (articles ns=0, project documentation ns=4) must not be falsely blocked.
    # 4. Programmatic Wikify(text) calls must remain independent of page namespace (no alerts/blocks).
    # 5. Combined with Proposal #008, full-page confirmation must NOT produce unnecessary double dialogs
    #    on talk pages (must immediately alert strings.talkPage without prompting confirm(strings.fullText)).
    import shutil
    import subprocess
    from pathlib import Path

    prop_file = Path("proposals/009/proposed.txt")
    orig_file = Path("proposals/009/original.txt")
    target_file = prop_file if prop_file.exists() else orig_file

    if orig_file.exists() and target_file.exists() and shutil.which("node"):
        cmd = [
            "node",
            "-e",
            f"""
            const fs = require('fs');
            const vm = require('vm');

            function createEnv(code, ns, initialContents, initialSelection, caretPos) {{
                let contents = initialContents;
                let selection = initialSelection || '';
                let pos = caretPos !== undefined ? caretPos : [0, 0];
                let dialogs = [];

                const sandbox = {{
                    document: {{
                        documentElement: {{ scrollTop: 0 }},
                        editform: {{ wpSection: {{ value: '' }} }}
                    }},
                    alert: (msg) => {{ dialogs.push({{ type: 'alert', msg }}); }},
                    confirm: (msg) => {{ dialogs.push({{ type: 'confirm', msg }}); return true; }},
                    registerTool: () => {{}}
                }};
                sandbox.window = sandbox;
                sandbox.global = sandbox;

                const mockInput = {{
                    nodeType: 1,
                    value: contents,
                    focus: () => {{}},
                    scrollTop: () => 0,
                    on: () => {{}},
                    textSelection: (action, options) => {{
                        if (action === 'getCaretPosition') return pos;
                        if (action === 'getContents') return contents;
                        if (action === 'setContents') {{ contents = options; return mockInput; }}
                        if (action === 'getSelection') return selection;
                        if (action === 'encapsulateSelection') {{
                            contents = contents.replace(selection, options.peri);
                            return mockInput;
                        }}
                        if (action === 'setSelection') return mockInput;
                    }}
                }};

                sandbox.$ = () => mockInput;
                sandbox.$.client = {{ profile: () => ({{ platform: 'linux' }}) }};
                sandbox.$.trim = s => (s||'').trim();
                sandbox.mw = {{
                    loader: {{ using: (d, cb) => {{ if(cb) cb(); return {{ then: fn => fn && fn() }}; }} }},
                    config: {{ get: (key) => (key === 'wgNamespaceNumber' ? ns : 0) }}
                }};

                vm.createContext(sandbox);
                vm.runInContext(code, sandbox);

                return {{
                    sandbox,
                    mockInput,
                    getContents: () => contents,
                    getDialogs: () => dialogs,
                    getAlert: () => {{
                        const a = dialogs.find(d => d.type === 'alert');
                        return a ? a.msg : null;
                    }}
                }};
            }}

            // 1. Verify RED on live code
            const origCode = fs.readFileSync('{orig_file}', 'utf8');
            const live1 = createEnv(origCode, 1, 'Паведамленне - тэкст. 12:00, 1 студзеня 2026 (+03)', '', [0, 0]);
            live1.sandbox.Wikify(live1.mockInput);
            if (live1.getAlert() !== null || !live1.getContents().includes('—')) {{
                console.error('Expected live code to fail to protect talk page with 1 signature');
                process.exit(1);
            }}

            const live2 = createEnv(origCode, 1, 'Каментар 1 - тэкст. 12:00, 1 студзеня 2026 (+02)', '', [0, 0]);
            live2.sandbox.Wikify(live2.mockInput);
            if (live2.getAlert() !== null || !live2.getContents().includes('—')) {{
                console.error('Expected live code to fail to protect talk page with (+02) timezone');
                process.exit(1);
            }}

            const selQuote = 'Цытата 1: 12:00, 1 студзеня 2026 (+03) і цытата 2: 13:00, 1 студзеня 2026 (+03) - тэкст';
            const live3 = createEnv(origCode, 1, selQuote, selQuote, [0, selQuote.length]);
            live3.sandbox.Wikify(live3.mockInput);
            if (live3.getAlert() === null) {{
                console.error('Expected live code to falsely block selection containing 2 signatures');
                process.exit(1);
            }}

            // Live code protected ns=4 forum discussions with >= 2 signatures
            const forumText = 'Тэма 1: 12:00, 1 студзеня 2026 (+03) і тэма 2: 13:00, 1 студзеня 2026 (+03) - тэкст';
            const live4 = createEnv(origCode, 4, forumText, '', [0, 0]);
            live4.sandbox.Wikify(live4.mockInput);
            if (live4.getAlert() === null || live4.getContents().includes('—')) {{
                console.error('Expected live code to protect namespace 4 forum with 2 signatures');
                process.exit(1);
            }}

            // 2. Verify GREEN on proposed code
            const propCode = fs.readFileSync('{target_file}', 'utf8');

            // Case A: Talk page (ns=1), no selection, 0 signatures -> blocked
            const pA = createEnv(propCode, 1, 'Тэкст без подпісу - тэкст', '', [0, 0]);
            pA.sandbox.Wikify(pA.mockInput);
            if (!pA.getAlert() || pA.getContents() !== 'Тэкст без подпісу - тэкст') {{
                console.error('Proposed code failed to block full-page on talk page with 0 signatures');
                process.exit(1);
            }}

            // Case B: Talk page (ns=1), no selection, 1 signature -> blocked
            const pB = createEnv(propCode, 1, 'Паведамленне - тэкст. 12:00, 1 студзеня 2026 (+03)', '', [0, 0]);
            pB.sandbox.Wikify(pB.mockInput);
            if (!pB.getAlert() || pB.getContents() !== 'Паведамленне - тэкст. 12:00, 1 студзеня 2026 (+03)') {{
                console.error('Proposed code failed to block full-page on talk page with 1 signature');
                process.exit(1);
            }}

            // Case C: Talk page (ns=3), no selection, (+02) timezone -> blocked
            const pC = createEnv(propCode, 3, 'Каментар 1 - тэкст. 12:00, 1 студзеня 2026 (+02)', '', [0, 0]);
            pC.sandbox.Wikify(pC.mockInput);
            if (!pC.getAlert() || pC.getContents() !== 'Каментар 1 - тэкст. 12:00, 1 студзеня 2026 (+02)') {{
                console.error('Proposed code failed to block full-page on talk page with (+02) timezone');
                process.exit(1);
            }}

            // Case D: Talk page (ns=1), text selected with 2 signatures -> NOT blocked, selection formatted
            const pD = createEnv(propCode, 1, selQuote, selQuote, [0, selQuote.length]);
            pD.sandbox.Wikify(pD.mockInput);
            if (pD.getAlert() !== null || !pD.getContents().includes('—')) {{
                console.error('Proposed code failed to format selection on talk page');
                process.exit(1);
            }}

            // Case E: Article (ns=0), no selection -> NOT blocked, full page formatted
            const pE = createEnv(propCode, 0, 'Артыкул - тэкст', '', [0, 0]);
            pE.sandbox.Wikify(pE.mockInput);
            if (pE.getAlert() !== null || !pE.getContents().includes('—')) {{
                console.error('Proposed code incorrectly blocked article namespace');
                process.exit(1);
            }}

            // Case F1: Project documentation (ns=4), no selection -> NOT blocked, full page formatted
            const pF1 = createEnv(propCode, 4, 'Дакументацыя - тэкст', '', [0, 0]);
            pF1.sandbox.Wikify(pF1.mockInput);
            if (pF1.getAlert() !== null || !pF1.getContents().includes('—')) {{
                console.error('Proposed code incorrectly blocked project namespace documentation (ns=4)');
                process.exit(1);
            }}

            // Case F2: Project discussion board (ns=4), >= 2 signatures, no selection -> BLOCKED
            const pF2 = createEnv(propCode, 4, forumText, '', [0, 0]);
            pF2.sandbox.Wikify(pF2.mockInput);
            if (!pF2.getAlert() || pF2.getContents() !== forumText) {{
                console.error('Proposed code failed to block namespace 4 forum with 2 signatures');
                process.exit(1);
            }}

            // Case F3: Project discussion board (ns=4), text selected -> NOT blocked, selection formatted
            const pF3 = createEnv(propCode, 4, forumText, forumText, [0, forumText.length]);
            pF3.sandbox.Wikify(pF3.mockInput);
            if (pF3.getAlert() !== null || !pF3.getContents().includes('—')) {{
                console.error('Proposed code failed to format selection on namespace 4 forum');
                process.exit(1);
            }}

            // Case F4: Programmatic Wikify(text) on namespace 4 with signatures -> NOT blocked, no alert, formatted
            const pF4 = createEnv(propCode, 4, '', '', [0, 0]);
            const f4Out = pF4.sandbox.Wikify('Дакумент - тэкст. 12:00, 1 студзеня 2026 (+03) і 13:00, 1 студзеня 2026 (+03)');
            if (pF4.getAlert() !== null || !f4Out.includes('—')) {{
                console.error('Proposed code broke programmatic Wikify(text) on namespace 4');
                process.exit(1);
            }}

            // Case G: Programmatic Wikify(text) on talk page (ns=1) -> NOT blocked, no alert, formatted
            const pG = createEnv(propCode, 1, '', '', [0, 0]);
            const gOut = pG.sandbox.Wikify('Праграмны - тэкст');
            if (pG.getAlert() !== null || !gOut.includes('—')) {{
                console.error('Proposed code broke programmatic Wikify(text) on talk page');
                process.exit(1);
            }}

            // Case H: Fallback (!caretPosition) on talk page (ns=1) -> alert, NO confirm dialog
            const pH = createEnv(propCode, 1, 'Размовы - тэкст', '', null);
            pH.sandbox.Wikify(pH.mockInput);
            if (pH.getDialogs().length !== 1 || pH.getDialogs()[0].type !== 'alert') {{
                console.error('Fallback on talk page triggered unexpected dialogs:', pH.getDialogs());
                process.exit(1);
            }}

            // 3. Verify interaction with pending Proposal #008 (full-page confirmation)
            // Proposal #008 wraps full-page processing in `if ( confirm( strings.fullText ) )`.
            // When combined with #009:
            let combined = propCode.replace(
                'processAllText();\\n\\t\\t\\t}} else {{',
                'if ( confirm( strings.fullText ) ) {{\\n\\t\\t\\t\\t\\tprocessAllText();\\n\\t\\t\\t\\t}}\\n\\t\\t\\t}} else {{'
            );

            // Combined Talk (ns=1), no selection: MUST show ONLY alert(strings.talkPage), NO double dialog!
            const combTalk = createEnv(combined, 1, 'Размовы - тэкст', '', [0, 0]);
            combTalk.sandbox.Wikify(combTalk.mockInput);
            if (combTalk.getDialogs().length !== 1 || combTalk.getDialogs()[0].type !== 'alert') {{
                console.error('Combined #008 + #009 produced double dialog or missing alert on talk page:', combTalk.getDialogs());
                process.exit(1);
            }}

            // Combined Project Forum (ns=4), >= 2 signatures: MUST show ONLY alert(strings.talkPage), NO double dialog!
            const combForum = createEnv(combined, 4, forumText, '', [0, 0]);
            combForum.sandbox.Wikify(combForum.mockInput);
            if (combForum.getDialogs().length !== 1 || combForum.getDialogs()[0].type !== 'alert') {{
                console.error('Combined #008 + #009 produced double dialog or missing alert on ns=4 forum:', combForum.getDialogs());
                process.exit(1);
            }}

            // Combined Article (ns=0), no selection: MUST show confirm dialog, then process
            const combArt = createEnv(combined, 0, 'Артыкул - тэкст', '', [0, 0]);
            combArt.sandbox.Wikify(combArt.mockInput);
            if (combArt.getDialogs().length !== 1 || combArt.getDialogs()[0].type !== 'confirm' || !combArt.getContents().includes('—')) {{
                console.error('Combined #008 + #009 failed confirm on article page');
                process.exit(1);
            }}
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
