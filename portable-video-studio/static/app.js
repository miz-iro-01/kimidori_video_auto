// Video Studio Hub - Portable Controller (NO EMOJIS)

let currentStoryboard = [];
let currentSpeakers = [];
let pollingInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    loadUserConfig();
    restoreProjectState();

    const scriptTextarea = document.getElementById('script-input');
    if (scriptTextarea) {
        scriptTextarea.addEventListener('input', () => {
            onScriptContentChanged();
        });
    }

    // iframe内の場合、親プラットフォーム連携ボタンを表示
    if (window.parent && window.parent !== window) {
        const syncBtn = document.getElementById('btn-sync-host');
        if (syncBtn) syncBtn.style.display = 'inline-block';
    }

    // 親ウィンドウからのメッセージ受信（サロンや別ツールからの台本受取）
    window.addEventListener('message', (event) => {
        if (event.data?.type === 'LOAD_SCRIPT' && event.data?.script) {
            const el = document.getElementById('script-input');
            if (el) {
                el.value = event.data.script;
                onScriptContentChanged();
                updateStatus('親プラットフォームから台本を読み込みました');
            }
        }
    });
});

let parseDebounceTimer = null;

function onScriptContentChanged() {
    const text = document.getElementById('script-input').value.trim();
    const btnStart = document.getElementById('btn-start');

    if (text.length > 30) {
        if (parseDebounceTimer) clearTimeout(parseDebounceTimer);
        parseDebounceTimer = setTimeout(() => {
            autoParseStoryboard();
        }, 500);
    } else {
        if (btnStart) btnStart.disabled = true;
    }
}

async function autoParseStoryboard() {
    const script = document.getElementById('script-input').value.trim();
    if (!script || script.length < 30) return;

    const video_type = document.querySelector('input[name="video_type"]:checked')?.value || 'long';
    const format = (video_type === 'short') ? '9:16' : '16:9';
    const style = document.getElementById('style-select')?.value || 'manga_color';
    const genre = document.getElementById('genre-select')?.value || 'business';
    const thumbnail_style = document.getElementById('thumbnail-style-select')?.value || 'split';

    updateStatus('台本を自動解析して絵コンテを展開中...');

    try {
        const res = await fetch('/api/parse-storyboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script, format, video_type, style, genre, thumbnail_style })
        });
        const data = await res.json();
        if (data.storyboard && data.storyboard.length > 0) {
            currentStoryboard = data.storyboard;
            currentSpeakers = data.speakers || [];
            renderStoryboardTable(currentStoryboard);

            if (data.normalized_script && data.normalized_script !== script && (!script.includes('[00:') && !script.includes('[01:'))) {
                const scriptInput = document.getElementById('script-input');
                if (scriptInput) {
                    const startPos = scriptInput.selectionStart;
                    const endPos = scriptInput.selectionEnd;
                    scriptInput.value = data.normalized_script;
                    try { scriptInput.setSelectionRange(startPos, endPos); } catch (e) {}
                }
            }

            fetchAssets(false);
            updateStatus(`自動解析完了: 全 ${data.total_cuts || currentStoryboard.length} カット`);
            updateProgress(0, `全 ${data.total_cuts || currentStoryboard.length} カットの準備が完了しました。`);
        }
    } catch (e) {
        console.error('Auto parse error', e);
    }
}

async function restoreProjectState() {
    try {
        const statusRes = await fetch('/api/status');
        const statusData = await statusRes.json();
        if (statusData.status_text) {
            updateStatus(statusData.status_text);
            updateProgress(statusData.progress || 0, statusData.detail || '');
        }

        const res = await fetch('/api/current-storyboard');
        const data = await res.json();

        if (data.script && !document.getElementById('script-input').value) {
            document.getElementById('script-input').value = data.script;
        }

        if (data.storyboard && data.storyboard.length > 0) {
            currentStoryboard = data.storyboard;
            currentSpeakers = data.speakers || [];
            renderStoryboardTable(currentStoryboard);
        } else {
            onScriptContentChanged();
        }

        fetchAssets(statusData.is_running || false);
    } catch (e) {
        console.error('Restore project state error', e);
        onScriptContentChanged();
    }
}

function loadUserConfig() {
    const savedKey = localStorage.getItem('gemini_api_key');
    if (savedKey) {
        const keyEl = document.getElementById('gemini-api-key');
        if (keyEl) keyEl.value = savedKey;
    }
}

function saveApiKey(key) {
    localStorage.setItem('gemini_api_key', key.trim());
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick')?.includes(tabId));
    if (activeBtn) activeBtn.classList.add('active');

    const targetContent = document.getElementById(tabId);
    if (targetContent) targetContent.classList.add('active');

    if (tabId === 'tab-assets') {
        fetchAssets();
    }
}

function switchScriptMode(mode) {
    document.querySelectorAll('.mode-tab-btn').forEach(btn => btn.classList.remove('active'));
    const targetBtn = document.getElementById(`btn-mode-${mode}`);
    if (targetBtn) targetBtn.classList.add('active');

    const boxApi = document.getElementById('box-mode-api');
    const boxDirect = document.getElementById('box-mode-direct');

    if (boxApi) boxApi.style.display = (mode === 'api') ? 'flex' : 'none';
    if (boxDirect) boxDirect.style.display = (mode === 'direct') ? 'flex' : 'none';
}

function onVideoTypeChanged(type) {
    const isShort = (type === 'short');
    const themeInput = document.getElementById('api-theme-input');
    if (themeInput) {
        themeInput.placeholder = isShort 
            ? "ショート動画テーマ (例: 江戸のウーバーイーツ / 9割が知らない真実)"
            : "リサーチテーマ (例: 40代から豊かになる知恵 / 人生の幸福と富の習慣)";
    }
    updateStatus(`動画タイプ変更: ${isShort ? 'ショート動画 (60秒 / 9:16縦型)' : '長尺動画 (15〜20分 / 16:9横型)'}`);
    onScriptContentChanged();
}

async function generateScriptViaApi() {
    const theme = document.getElementById('api-theme-input').value.trim();
    if (!theme) {
        alert('リサーチテーマを入力してください。');
        return;
    }

    const apiKey = document.getElementById('gemini-api-key').value.trim();
    const genre = document.getElementById('genre-select').value;
    const videoType = document.querySelector('input[name="video_type"]:checked')?.value || 'long';
    const isShort = (videoType === 'short');
    const lengthMinutes = isShort ? 1 : 18;

    updateStatus(`AIリサーチ台本執筆中: 「${theme}」...`);
    updateProgress(20, '全章の構成・カットタイムスタンプを並列リサーチ執筆中...');

    let curProgress = 20;
    const timer = setInterval(() => {
        if (curProgress < 90) {
            curProgress += 10;
            updateProgress(curProgress, `リサーチ執筆中... [進捗: ${curProgress}%]`);
        }
    }, 2000);

    try {
        const res = await fetch('/api/generate-ai-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme, genre, api_key: apiKey, length_minutes: lengthMinutes, video_type: videoType })
        });
        clearInterval(timer);
        const data = await res.json();

        if (data.status === 'success' && data.script) {
            document.getElementById('script-input').value = data.script;
            updateProgress(100, '台本生成完了。絵コンテを自動展開します。');
            updateStatus('台本生成完了');
            onScriptContentChanged();
        } else {
            updateProgress(0, '生成失敗: ' + (data.message || 'エラーが発生しました'));
            updateStatus('エラー');
            alert('台本生成エラー: ' + (data.message || 'APIキーまたは通信状況を確認してください'));
        }
    } catch (e) {
        clearInterval(timer);
        updateProgress(0, '通信エラー: ' + e);
        updateStatus('エラー');
        alert('通信エラー: ' + e);
    }
}

function loadSampleScript() {
    const sample = `【タイトル】：豊かになる人の習慣
【選定テーマ】：豊かになる人の習慣
■ 動画タイプ: 長尺動画 (18分 / 16:9横型)
■ 動画ジャンル: ビジネス・解説 (business)

--- 【第1章：オープニング】 ---

[00:00] Cut_000
【話者】：【サムネイル画像】
【セリフ】：人生を変える秘密の習慣
【演出】：画面を左右に2分割。左に悩む男性、右に自信あふれる成功者の対比。

[00:04] Cut_001
【話者】：ナレーション
【セリフ】：なぜ同じ時間働いているのに、結果にこれほどの差が出るのでしょうか。
【演出】：都会の高層ビル街を早朝の光が照らす。

[00:10] Cut_002
【話者】：ナレーション
【セリフ】：その秘密は、日々の選択の積み重ねにありました。
【演出】：手帳を開いて一日の計画を立てる男性の手元。`;

    document.getElementById('script-input').value = sample;
    onScriptContentChanged();
}

function renderStoryboardTable(cuts) {
    const tbody = document.getElementById('storyboard-body');
    if (!tbody || !cuts || cuts.length === 0) return;

    tbody.innerHTML = cuts.map(c => {
        const cutNum = c.cut_number;
        const label = cutNum === 0 ? 'Cut_000 (サムネ)' : `Cut_${String(cutNum).padStart(3, '0')}`;
        const time = c.start_time || '00:00';
        const spk = c.speaker || 'ナレーション';
        const dialogue = c.dialogue || '-';
        const prompt = c.visual_prompt || c.scene_description || '-';
        const camera = c.camera_work || '-';
        const fmt = c.is_video ? '動画 (MP4)' : (cutNum === 0 ? 'サムネイル' : '画像 (PNG)');

        return `
            <tr>
                <td style="font-weight: 700; color: var(--accent-cyan);">${label}</td>
                <td style="font-family: var(--font-mono);">${time}</td>
                <td style="color: #93c5fd;">${spk}</td>
                <td>${dialogue}</td>
                <td style="color: var(--text-secondary); font-size: 11px;">${prompt}</td>
                <td style="color: var(--text-muted); font-size: 11px;">${camera}</td>
                <td><span class="badge" style="background: ${c.is_video ? '#8b5cf6' : '#2563eb'}; color:#fff; padding: 2px 6px; font-size: 10px; border-radius: 4px;">${fmt}</span></td>
            </tr>
        `;
    }).join('');

    const btnStart = document.getElementById('btn-start');
    if (btnStart) btnStart.disabled = false;
}

// ==========================================
// 素材生成 ＆ リアルタイムサムネイル反映エンジン
// ==========================================
async function startGeneration() {
    const script = document.getElementById('script-input').value.trim();
    if (!script) {
        alert('台本を入力してください。');
        return;
    }

    const video_type = document.querySelector('input[name="video_type"]:checked')?.value || 'long';
    const format = (video_type === 'short') ? '9:16' : '16:9';
    const style = document.getElementById('style-select')?.value || 'manga_color';
    const genre = document.getElementById('genre-select')?.value || 'business';
    const thumbnail_style = document.getElementById('thumbnail-style-select')?.value || 'split';

    updateStatus('素材生成プロセスを起動中...');
    updateProgress(10, '素材生成を開始します。生成された画像が順次ここに表示されます...');

    // 自動で生成アセットタブに切り替えてリアルタイム描画を見せる！
    switchTab('tab-assets');

    try {
        const res = await fetch('/api/start-production', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script, format, video_type, style, genre, thumbnail_style })
        });
        const data = await res.json();
        if (data.status === 'started' || data.status === 'already_running') {
            startStatusPolling();
        }
    } catch (e) {
        alert('生成開始エラー: ' + e);
    }
}

function startStatusPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();

            updateProgress(data.progress || 0, data.detail || '素材生成中...');
            updateStatus(data.status_text || '生成実行中');

            // 毎回のポーリングで最新の生成画像をグリッドに即座に反映！
            fetchAssets(data.is_running);

            if (data.is_completed) {
                clearInterval(pollingInterval);
                updateProgress(100, '全カットの素材生成が完了しました。');
                fetchAssets(false);
            } else if (!data.is_running) {
                clearInterval(pollingInterval);
                updateStatus(data.status_text || '待機中');
                fetchAssets(false);
            }
        } catch (e) {
            console.error('Polling error', e);
        }
    }, 1500);
}

async function fetchAssets(isRunning = false) {
    try {
        const res = await fetch('/api/assets');
        const data = await res.json();
        const grid = document.getElementById('asset-grid');
        const tabBtn = document.querySelector("button[onclick*='assets']");

        updateResumeState(data.images || [], isRunning);

        if (!data.images || data.images.length === 0) {
            if (isRunning) {
                grid.innerHTML = '<div class="text-muted text-center grid-empty" style="padding: 40px;">素材を生成中です...<br><span style="font-size: 13px; color: #888;">（画像・動画が生成され次第、順次ここにリアルタイム表示されます）</span></div>';
            } else {
                grid.innerHTML = '<div class="text-muted text-center grid-empty">生成されたアセットがありません。</div>';
            }
            if (tabBtn) tabBtn.innerText = '生成アセット一覧';
            return;
        }

        if (tabBtn) {
            tabBtn.innerText = `生成アセット一覧 (${data.images.length}件)`;
        }

        grid.innerHTML = data.images.map(img => {
            const basename = img.name.split('/').pop().split('\\').pop();
            let label = basename;
            let cutNum = 0;
            const m = basename.match(/^(\d+)/);
            if (m) {
                cutNum = parseInt(m[1]);
            }

            const isVideo = img.is_video || basename.endsWith('.mp4');

            if (basename.startsWith('000') || basename === '00.png') {
                label = 'Cut_000: サムネイル';
            } else if (isVideo) {
                label = `Cut_${String(cutNum).padStart(3, '0')}: 動画クリップ`;
            } else {
                label = `Cut_${String(cutNum).padStart(3, '0')}: 画像アセット`;
            }

            const mediaHtml = isVideo ?
                `<video src="${img.url}" class="asset-img" controls playsinline preload="metadata" style="background:#000;"></video>` :
                `<img src="${img.url}" class="asset-img" alt="${img.name}" loading="lazy">`;

            return `
                <div class="asset-card" id="card-cut-${cutNum}">
                    ${mediaHtml}
                    <div class="asset-info">
                        <span class="asset-id" style="font-weight: bold; font-size: 11px;">${label}</span>
                        <button class="btn btn-secondary btn-sm" onclick="regenerateCut(${cutNum}, this)" style="padding: 2px 6px; font-size: 10px; border-radius: 4px;" title="このカットのみを再生成">
                            再生成
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        renderTimelineEditor(data.images);
    } catch (e) {
        console.error('Fetch assets error', e);
    }
}

function updateResumeState(images, isRunning = false) {
    const btnStart = document.getElementById('btn-start');
    const resumeHint = document.getElementById('resume-hint');
    if (!btnStart) return;

    const scriptVal = document.getElementById('script-input')?.value.trim() || '';
    const hasScript = scriptVal.length > 30 || (currentStoryboard && currentStoryboard.length > 0);

    if (isRunning) {
        btnStart.disabled = true;
        btnStart.innerText = '素材自動生成中...';
        btnStart.style.background = '';
        if (resumeHint) resumeHint.style.display = 'none';
        return;
    }

    const cutNums = (images || []).map(img => {
        const basename = (img.name || '').split('/').pop().split('\\').pop();
        const m = basename.match(/^(\d+)/);
        return m ? parseInt(m[1]) : 0;
    }).filter(n => n > 0);

    const hasThumbnail = (images || []).some(img => {
        const basename = (img.name || '').split('/').pop().split('\\').pop();
        return basename.startsWith('000') || basename === '00.png';
    });

    if (cutNums.length > 0 || hasThumbnail) {
        const maxCut = cutNums.length > 0 ? Math.max(...cutNums) : 0;
        const nextCut = maxCut + 1;
        const nextCutStr = `Cut_${String(nextCut).padStart(3, '0')}`;

        btnStart.disabled = !hasScript;
        btnStart.innerText = `続きから生成を再開 (${nextCutStr}〜)`;
        btnStart.style.background = 'linear-gradient(135deg, #059669, #0284c7)';

        if (resumeHint) {
            resumeHint.style.display = 'block';
            let summaryParts = [];
            if (hasThumbnail) summaryParts.push('サムネイル(Cut_000)');
            if (cutNums.length > 0) summaryParts.push(`本編 (Cut_001〜${String(maxCut).padStart(3, '0')})`);
            resumeHint.innerHTML = `<strong>続きから再開可能:</strong> 既存の生成済み素材（${summaryParts.join('、')}）が保持されています。「続きから生成を再開」を押すと、${nextCutStr}から未生成のカットのみを続けて生成します。`;
        }
    } else {
        btnStart.disabled = !hasScript;
        btnStart.innerText = '素材生成開始';
        btnStart.style.background = '';
        if (resumeHint) resumeHint.style.display = 'none';
    }
}

async function regenerateCut(cutNumber, btnElement) {
    if (!confirm(`Cut_${String(cutNumber).padStart(3, '0')} を再生成しますか？`)) return;

    if (btnElement) {
        btnElement.disabled = true;
        btnElement.innerText = '生成中...';
    }

    try {
        const res = await fetch('/api/regenerate-cut', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cut_number: cutNumber })
        });
        const data = await res.json();
        if (data.status === 'success') {
            await fetchAssets(false);
        } else {
            alert('再生成失敗: ' + (data.message || 'エラー'));
        }
    } catch (e) {
        alert('通信エラー: ' + e);
    } finally {
        if (btnElement) {
            btnElement.disabled = false;
            btnElement.innerText = '再生成';
        }
    }
}

function renderTimelineEditor(images) {
    const container = document.getElementById('timeline-editor-list');
    if (!container || !currentStoryboard || currentStoryboard.length === 0) return;

    const mainCuts = currentStoryboard.filter(c => c.cut_number > 0);
    if (mainCuts.length === 0) return;

    container.innerHTML = mainCuts.map(cut => {
        const cutNum = cut.cut_number;
        const numStr = String(cutNum).padStart(3, '0');
        const dur = (cut.duration && !isNaN(cut.duration)) ? parseFloat(cut.duration).toFixed(1) : "4.0";
        
        const matchedImg = (images || []).find(img => {
            const basename = img.name.split('/').pop().split('\\').pop();
            return basename.startsWith(numStr);
        });

        const thumbUrl = matchedImg ? matchedImg.url : '';
        const thumbHtml = thumbUrl ?
            (matchedImg.is_video ?
                `<video src="${thumbUrl}" class="timeline-item-thumb" preload="metadata"></video>` :
                `<img src="${thumbUrl}" class="timeline-item-thumb" alt="Cut_${numStr}">`
            ) :
            `<div class="timeline-item-thumb-placeholder">未生成</div>`;

        return `
            <div class="timeline-item-card" id="timeline-cut-${cutNum}">
                ${thumbHtml}
                <div class="timeline-item-details">
                    <div class="timeline-item-header">
                        <span class="timeline-item-id">Cut_${numStr}</span>
                        <span class="timeline-item-speaker">${cut.speaker || 'ナレーション'}</span>
                    </div>
                    <div class="timeline-item-dialogue">${cut.dialogue || '-'}</div>
                </div>
                <div class="timeline-item-controls">
                    <label style="font-size: 11px; color: var(--text-muted);">秒数:
                        <input type="number" step="0.5" min="1.0" max="60.0" class="form-input mini-input timeline-dur-input" 
                               data-cut="${cutNum}" value="${dur}" style="width: 54px; display: inline-block; margin-left: 4px;">
                    </label>
                </div>
            </div>
        `;
    }).join('');
}

function resetStudio() {
    if (!confirm('スタジオの入力と現在のステータスを初期化しますか？')) return;
    document.getElementById('script-input').value = '';
    currentStoryboard = [];
    currentSpeakers = [];
    document.getElementById('storyboard-body').innerHTML = '<tr><td colspan="7" class="text-muted text-center" style="padding: 40px;">台本を入力・生成すると、ここに全カットの絵コンテが自動展開されます。</td></tr>';
    document.getElementById('asset-grid').innerHTML = '<div class="text-muted text-center grid-empty">生成されたアセットがありません。</div>';
    updateProgress(0, '待機中: 台本を入力・生成すると自動解析されます。');
    updateStatus('待機中');
    const btnStart = document.getElementById('btn-start');
    if (btnStart) {
        btnStart.disabled = true;
        btnStart.innerText = '素材生成開始';
        btnStart.style.background = '';
    }
}

function updateStatus(text) {
    const el = document.getElementById('system-status-text');
    if (el) el.innerText = text;
}

function updateProgress(percent, detail) {
    const bar = document.getElementById('progress-bar-fill');
    const percentEl = document.getElementById('progress-percent');
    const detailEl = document.getElementById('progress-detail');

    if (bar) bar.style.width = `${percent}%`;
    if (percentEl) percentEl.innerText = `${percent}%`;
    if (detailEl) detailEl.innerText = detail;
}

// 親プラットフォームへの下書き連携
function sendDraftToHost() {
    const script = document.getElementById('script-input')?.value || '';
    if (!script) {
        alert('保存する台本がありません。');
        return;
    }
    if (window.parent && window.parent !== window) {
        window.parent.postMessage({
            type: 'SAVE_DRAFT',
            title: '動画台本_' + new Date().toISOString().slice(0, 10),
            content: script,
            storyboard: currentStoryboard,
            targetCollection: 'contents'
        }, '*');
        updateStatus('親プラットフォームへ下書きを送信しました');
    }
}
