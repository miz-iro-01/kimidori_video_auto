/**
 * KIMIDORI Studio Pro (Phase 2)
 * Jet-cut / Pexels B-roll / bottom-right wipe (live face + talking character)
 * Studio telop clips / BGM track. Extends the Pro timeline editor in app.js
 * without changing its existing handlers. State is stored in editorState.studio.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const base = () => window.apiClient.baseUrl;
  const fullUrl = (u) => (!u ? '' : (u.startsWith('http') ? u : `${base()}${u}`));
  const STYLE_COLORS = {
    shorts_impact_yellow: '#FFE600', shorts_crimson_flame: '#FFF5D6', shorts_gold_luxury: '#FFD700',
    shorts_neon_cyber: '#00F5FF', shorts_clean_white: '#FFFFFF'
  };
  const STOP = new Set(['こと', 'もの', 'ため', 'これ', 'それ', 'あれ', 'ここ', 'そこ', 'よう', 'ところ', 'など', 'です', 'ます', 'する', 'した', 'いる', 'ある', 'なる', 'できる', 'という', 'そして', 'しかし', 'だから', 'また']);

  class StudioPro {
    constructor(app) {
      this.app = app;
      this.envCache = new Map();
      this.audioCtx = null;
      this.raf = 0;
      this.hookApp();
      this.bindControls();
    }

    get st() { return this.app.editorState; }

    hookApp() {
      const app = this.app;
      const origOpen = app.openProVideoEditor.bind(app);
      app.openProVideoEditor = async (...args) => {
        await origOpen(...args);
        if (app.editorState) this.onOpened();
      };
      const origTracks = app.renderEditorTimelineTracks.bind(app);
      app.renderEditorTimelineTracks = () => {
        origTracks();
        this.renderExtraTracks();
      };
    }

    ensure() {
      const st = this.st;
      if (!st) return null;
      if (!st.studio) {
        const wide = st.aspect_ratio === '16:9';
        st.studio = {
          wipe: { enabled: false, mode: 'character', shape: 'circle', size_pct: wide ? 20 : 26, x_pct: wide ? 86 : 80, y_pct: wide ? 74 : 62, mouth_overlay: true, border: true, face_url: '', char_url: '', face_name: '', char_name: '' },
          broll: [], telops: [], telops_override: false, bgm_muted: false
        };
        // Default monetization BGM track at 15% for a newly loaded project
        st.bgm_volume = 0.15;
        if (!st.bgm_choice || st.bgm_choice === 'none') st.bgm_choice = 'builtin:upbeat_business';
      }
      return st.studio;
    }

    toast(msg, type = 'info') { this.app.showToast(msg, type); }

    setBusy(btn, busy, label) {
      if (!btn) return;
      if (busy) {
        btn._orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-spinner"></span><span>${label || '処理中...'}</span>`;
      } else {
        btn.disabled = false;
        if (btn._orig) btn.innerHTML = btn._orig;
      }
    }

    timeline() {
      let t = 0;
      return (this.st?.scenes || []).map((sc, i) => {
        const en = sc.enabled !== false;
        const dur = en ? (parseFloat(sc.duration) || 0) : 0;
        const o = { sc, i, start: t, dur, enabled: en };
        t += dur;
        return o;
      });
    }

    total() { return this.timeline().reduce((a, x) => a + x.dur, 0) || 1; }

    refreshApp() {
      this.app.updateEditorProjectHeader();
      this.app.renderEditorTimelineTracks();
    }

    // ------------------------------------------------------------------ open
    onOpened() {
      if (!this.ensure()) return;
      this.syncControls();
      this.renderBrollList();
      this.renderTelopList();
      this.updateWipePreview();
      this.renderExtraTracks();
      this.startPreviewLoop();
    }

    syncControls() {
      const s = this.st.studio;
      const w = s.wipe;
      $('studioWipeEnabled').checked = !!w.enabled;
      $('studioWipeMode').value = w.mode;
      $('studioWipeShape').value = w.shape;
      $('studioWipeSize').value = w.size_pct;
      $('studioWipeX').value = w.x_pct;
      $('studioWipeY').value = w.y_pct;
      $('studioWipeMouth').checked = w.mouth_overlay !== false;
      this.updateWipeLabels();
      const info = [];
      if (w.char_name) info.push(`キャラ画像: ${w.char_name}`);
      if (w.face_name) info.push(`顔映像: ${w.face_name}`);
      $('studioWipeFileInfo').textContent = info.join(' / ') || '素材未選択';
      $('studioTelopsOverride').checked = !!s.telops_override;
      this.syncBgm();
      const bgmSel = $('editorGlobalBgmSelect');
      if (bgmSel && this.st.bgm_choice) bgmSel.value = this.st.bgm_choice;
    }

    syncBgm() {
      const pct = Math.round((parseFloat(this.st.bgm_volume ?? 0.15)) * 100);
      $('studioBgmVol').value = pct;
      $('studioBgmVolLabel').textContent = `${pct}%`;
      const gs = $('editorGlobalBgmVolSlider');
      const gl = $('editorGlobalBgmVolLabel');
      if (gs) gs.value = String(Math.min(50, pct));
      if (gl) gl.textContent = `${pct}%`;
      const muted = !!this.st.studio.bgm_muted;
      $('btnStudioBgmMute').textContent = muted ? 'ミュート解除' : 'ミュート';
      const sel = $('editorGlobalBgmSelect');
      const label = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : (this.st.bgm_choice || '--');
      $('studioBgmInfo').textContent = `BGM: ${label}${muted ? '（ミュート中）' : ''}`;
    }

    updateWipeLabels() {
      const w = this.st.studio.wipe;
      $('studioWipeSizeLabel').textContent = `${w.size_pct}%`;
      $('studioWipeXLabel').textContent = `${w.x_pct}%`;
      $('studioWipeYLabel').textContent = `${w.y_pct}%`;
    }

    // ----------------------------------------------------------- bind events
    bindControls() {
      const on = (id, ev, fn) => $(id)?.addEventListener(ev, fn);

      on('studioJetThreshold', 'input', (e) => { $('studioJetThresholdLabel').textContent = `${e.target.value} dB`; });
      on('studioJetMinSilence', 'input', (e) => { $('studioJetMinLabel').textContent = `${parseFloat(e.target.value).toFixed(2)}秒`; });
      on('btnStudioJetCut', 'click', () => this.runJetCut());
      on('btnStudioJetReset', 'click', () => this.resetJetCut());
      on('btnStudioBrollAuto', 'click', () => this.autoBroll());

      // wipe
      const wipeSync = () => {
        const s = this.ensure();
        if (!s) return;
        const w = s.wipe;
        w.enabled = $('studioWipeEnabled').checked;
        w.mode = $('studioWipeMode').value;
        w.shape = $('studioWipeShape').value;
        w.size_pct = parseInt($('studioWipeSize').value, 10);
        w.x_pct = parseInt($('studioWipeX').value, 10);
        w.y_pct = parseInt($('studioWipeY').value, 10);
        w.mouth_overlay = $('studioWipeMouth').checked;
        this.updateWipeLabels();
        this.updateWipePreview();
        this.renderExtraTracks();
      };
      ['studioWipeEnabled', 'studioWipeShape', 'studioWipeMode', 'studioWipeSize', 'studioWipeX', 'studioWipeY', 'studioWipeMouth']
        .forEach((id) => { on(id, 'input', wipeSync); on(id, 'change', wipeSync); });
      on('fileStudioChar', 'change', (e) => this.uploadWipeAsset(e, 'character_image'));
      on('fileStudioFace', 'change', (e) => this.uploadWipeAsset(e, 'face_video'));
      this.bindWipeDrag();

      // telops
      on('btnStudioTelopAuto', 'click', () => this.autoTelops());
      on('btnStudioTelopAdd', 'click', () => this.addTelop());
      on('studioTelopsOverride', 'change', (e) => { const s = this.ensure(); if (s) s.telops_override = e.target.checked; });

      // bgm
      on('studioBgmVol', 'input', (e) => {
        if (!this.ensure()) return;
        this.st.bgm_volume = parseInt(e.target.value, 10) / 100;
        this.syncBgm();
        this.renderExtraTracks();
      });
      on('btnStudioBgmMute', 'click', () => this.toggleBgmMute());
      on('fileStudioBgm', 'change', (e) => this.uploadBgm(e));
      on('editorGlobalBgmSelect', 'change', () => { if (this.st?.studio) { this.syncBgm(); this.renderExtraTracks(); } });
      on('editorGlobalBgmVolSlider', 'input', () => { if (this.st?.studio) setTimeout(() => { this.syncBgm(); this.renderExtraTracks(); }, 0); });
    }

    // -------------------------------------------------------------- jet-cut
    async getAudioBuffer(sc) {
      const key = fullUrl(sc.audio_url).split('?')[0];
      const hit = this.envCache.get(key);
      if (hit) return hit;
      const res = await fetch(fullUrl(sc.audio_url));
      if (!res.ok) throw new Error('音声の取得に失敗しました');
      const arr = await res.arrayBuffer();
      const ctx = this.audioCtx || (this.audioCtx = new (window.AudioContext || window.webkitAudioContext)());
      const ab = await ctx.decodeAudioData(arr);
      const ch = ab.getChannelData(0);
      const win = Math.max(1, Math.floor(ab.sampleRate * 0.01));
      const rms = new Float32Array(Math.floor(ch.length / win));
      for (let i = 0; i < rms.length; i++) {
        let acc = 0;
        for (let j = 0; j < win; j++) { const v = ch[i * win + j]; acc += v * v; }
        rms[i] = Math.sqrt(acc / win);
      }
      const out = { rms, total: ab.duration, step: 0.01 };
      this.envCache.set(key, out);
      return out;
    }

    computeKeep(env, thrDb, minSil) {
      const thr = Math.max(Math.pow(10, thrDb / 20), 0.0005);
      const pad = 0.06;
      const n = env.rms.length;
      const silences = [];
      let runStart = -1;
      for (let i = 0; i <= n; i++) {
        const quiet = i < n && env.rms[i] < thr;
        if (quiet && runStart < 0) runStart = i;
        if (!quiet && runStart >= 0) {
          const a = runStart * env.step;
          const b = i * env.step;
          if (b - a >= minSil) silences.push([a, b]);
          runStart = -1;
        }
      }
      const remove = silences.map(([a, b]) => [a <= env.step ? 0 : a + pad, b >= env.total - env.step ? env.total : b - pad])
        .filter(([a, b]) => b - a > 0.02);
      const keep = [];
      let cursor = 0;
      remove.forEach(([a, b]) => {
        if (a > cursor + 0.02) keep.push([+cursor.toFixed(3), +a.toFixed(3)]);
        cursor = Math.max(cursor, b);
      });
      if (env.total > cursor + 0.02) keep.push([+cursor.toFixed(3), +env.total.toFixed(3)]);
      return { keep, removed: remove.reduce((x, [a, b]) => x + (b - a), 0) };
    }

    async runJetCut() {
      if (!this.ensure()) return this.toast('編集スタジオを開いてから実行してください', 'warning');
      const btn = $('btnStudioJetCut');
      const thrDb = parseInt($('studioJetThreshold').value, 10);
      const minSil = parseFloat($('studioJetMinSilence').value);
      this.setBusy(btn, true, '音声波形を解析中...');
      let removedTotal = 0;
      let touched = 0;
      try {
        for (const sc of this.st.scenes) {
          if (sc.enabled === false || !sc.audio_url) continue;
          const env = await this.getAudioBuffer(sc);
          const { keep, removed } = this.computeKeep(env, thrDb, minSil);
          if (removed < 0.05 || !keep.length) continue;
          if (sc.jet_orig_duration == null) sc.jet_orig_duration = parseFloat(sc.duration) || env.total;
          sc.jet_keep = keep;
          sc.duration = +Math.max(0.5, sc.jet_orig_duration - removed).toFixed(2);
          removedTotal += removed;
          touched++;
        }
        $('studioJetResult').textContent = touched
          ? `${touched}カットの無音区間を除去し、合計 ${removedTotal.toFixed(1)}秒 短縮しました（前詰め済み）。再書き出しで反映されます。`
          : '指定条件に該当する無音区間はありませんでした。しきい値を上げて再実行できます。';
        this.refreshApp();
        this.toast(touched ? `ジェットカット完了: ${removedTotal.toFixed(1)}秒短縮` : '無音区間は見つかりませんでした', touched ? 'success' : 'info');
      } catch (err) {
        this.toast('ジェットカット失敗: ' + err.message, 'error');
      } finally {
        this.setBusy(btn, false);
      }
    }

    resetJetCut() {
      if (!this.st) return;
      let n = 0;
      this.st.scenes.forEach((sc) => {
        if (sc.jet_orig_duration != null) { sc.duration = sc.jet_orig_duration; n++; }
        delete sc.jet_keep;
        delete sc.jet_orig_duration;
      });
      $('studioJetResult').textContent = n ? `${n}カットを元の尺に戻しました。` : '戻す対象はありません。';
      this.refreshApp();
    }

    // -------------------------------------------------------------- B-roll
    extractKeywords(text, limit = 3) {
      const seg = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('ja', { granularity: 'word' }) : null;
      const freq = new Map();
      const add = (w) => {
        if (w.length < 2 || STOP.has(w) || /^[\u3040-\u309f]+$/.test(w) || /^[0-9０-９]+$/.test(w)) return;
        freq.set(w, (freq.get(w) || 0) + 1);
      };
      if (seg) {
        for (const s of seg.segment(text || '')) if (s.isWordLike) add(s.segment);
      } else {
        (text.match(/[\u30a0-\u30ff]{2,}|[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}/g) || []).forEach(add);
      }
      return [...freq.entries()]
        .map(([w, c]) => [w, c * Math.min(w.length, 6) * (/[\u30a0-\u30ff\u4e00-\u9fffA-Za-z]/.test(w) ? 1.5 : 1)])
        .sort((a, b) => b[1] - a[1]).slice(0, limit).map((x) => x[0]);
    }

    async searchPexels(query, kind) {
      const orient = this.st.aspect_ratio === '16:9' ? 'landscape' : 'portrait';
      const res = await fetch(`${base()}/api/studio/pexels-search`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query, kind, orientation: orient, per_page: 4,
          pexels_api_key: window.settingsManager.get('pexelsApiKey') || '',
          gemini_api_key: window.settingsManager.get('geminiApiKey') || ''
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || '素材検索に失敗しました');
      return data.items || [];
    }

    async autoBroll() {
      const s = this.ensure();
      if (!s) return this.toast('編集スタジオを開いてから実行してください', 'warning');
      if (!(window.settingsManager.get('pexelsApiKey') || '').trim()) {
        return this.toast('Pexels APIキーが未設定です。設定画面で登録してください', 'warning');
      }
      const btn = $('btnStudioBrollAuto');
      const kind = $('studioBrollKind').value;
      const userDur = Math.max(3, Math.min(5, parseFloat($('studioBrollDur').value) || 4));
      const every = Math.max(1, parseInt($('studioBrollEvery').value, 10) || 2);
      this.setBusy(btn, true, '素材を検索中...');
      try {
        const out = [];
        const tl = this.timeline().filter((x) => x.enabled);
        for (let k = 0; k < tl.length; k++) {
          if (k % every !== every - 1 && !(every === 1)) continue;
          const { sc, start, dur } = tl[k];
          const text = `${sc.narration || ''} ${sc.telop_text || ''}`;
          const query = (sc.search_query && String(sc.search_query).trim()) || this.extractKeywords(text, 1)[0];
          if (!query || dur < 2) continue;
          let items = [];
          try { items = await this.searchPexels(query, kind); } catch (e) { if (k === 0) throw e; }
          if (!items.length) continue;
          const it = items[0];
          const bStart = +(start + Math.min(0.8, dur * 0.2)).toFixed(2);
          const bDur = +Math.min(userDur, Math.max(1.5, dur - (bStart - start))).toFixed(2);
          out.push({ id: `br_${Date.now()}_${k}`, start: bStart, duration: bDur, keyword: query, kind: it.kind, url: it.url, thumb: it.thumb, enabled: true });
        }
        s.broll = out;
        this.renderBrollList();
        this.renderExtraTracks();
        this.toast(out.length ? `B-rollを${out.length}カ所に自動配置しました` : '該当する素材が見つかりませんでした', out.length ? 'success' : 'info');
      } catch (err) {
        this.toast('B-roll自動配置エラー: ' + err.message, 'error');
      } finally {
        this.setBusy(btn, false);
      }
    }

    renderBrollList() {
      const box = $('studioBrollList');
      if (!box || !this.st?.studio) return;
      const esc = (t) => this.app._escapeHtml(String(t ?? ''));
      box.innerHTML = this.st.studio.broll.map((b, i) => `
        <div class="studio-list-row" data-i="${i}">
          <input type="checkbox" data-f="enabled" ${b.enabled !== false ? 'checked' : ''}>
          ${b.thumb ? `<img src="${esc(b.thumb)}" alt="b-roll">` : ''}
          <span style="color:#c4b5fd;font-weight:700;">${esc(b.keyword)}</span>
          <label>開始<input type="number" class="form-input" data-f="start" step="0.1" min="0" value="${b.start}"></label>
          <label>秒数<input type="number" class="form-input" data-f="duration" step="0.5" min="1" max="8" value="${b.duration}"></label>
          <button type="button" class="btn btn-outline" data-f="del" style="padding:2px 8px;font-size:0.7rem;border-color:#ef4444;color:#f87171;">削除</button>
        </div>`).join('') || '<div style="font-size:0.74rem;color:#94a3b8;">B-rollは未配置です</div>';
      box.querySelectorAll('.studio-list-row').forEach((row) => {
        const i = parseInt(row.dataset.i, 10);
        row.querySelectorAll('[data-f]').forEach((el) => {
          const f = el.dataset.f;
          el.addEventListener(f === 'del' ? 'click' : 'input', () => {
            const arr = this.st.studio.broll;
            if (f === 'del') { arr.splice(i, 1); this.renderBrollList(); }
            else if (f === 'enabled') arr[i].enabled = el.checked;
            else arr[i][f] = parseFloat(el.value) || 0;
            this.renderExtraTracks();
          });
        });
      });
    }

    // ---------------------------------------------------------------- wipe
    async uploadAsset(kind, file) {
      const jobId = this.app.editorJobId;
      const fd = new FormData();
      fd.append('kind', kind);
      fd.append('file', file);
      const res = await fetch(`${base()}/api/studio/${encodeURIComponent(jobId)}/upload-asset`, { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'アップロードに失敗しました');
      return data;
    }

    async uploadWipeAsset(e, kind) {
      const file = e.target.files?.[0];
      e.target.value = '';
      const s = this.ensure();
      if (!file || !s) return;
      try {
        const data = await this.uploadAsset(kind, file);
        if (kind === 'character_image') { s.wipe.char_url = data.url; s.wipe.char_name = file.name; s.wipe.mode = 'character'; }
        else { s.wipe.face_url = data.url; s.wipe.face_name = file.name; s.wipe.mode = 'face'; }
        s.wipe.enabled = true;
        this.syncControls();
        this.updateWipePreview();
        this.renderExtraTracks();
        this.toast('ワイプ素材を登録しました', 'success');
      } catch (err) {
        this.toast('ワイプ素材エラー: ' + err.message, 'error');
      }
    }

    updateWipePreview() {
      const box = $('studioWipePreview');
      if (!box || !this.st?.studio) return;
      const w = this.st.studio.wipe;
      const face = $('studioWipeFaceEl');
      const charWrap = $('studioWipeCharWrap');
      const charImg = $('studioWipeCharImg');
      const src = w.mode === 'face' ? w.face_url : w.char_url;
      if (!w.enabled || !src) {
        box.style.display = 'none';
        face.pause();
        return;
      }
      box.style.display = 'block';
      box.className = `studio-wipe-preview ${w.shape === 'rounded' ? 'rounded' : 'circle'}`;
      box.style.width = `${w.size_pct}%`;
      box.style.aspectRatio = '1 / 1';
      box.style.left = `${w.x_pct}%`;
      box.style.top = `${w.y_pct}%`;
      box.style.transform = 'translate(-50%, -50%)';
      if (w.mode === 'face') {
        charWrap.style.display = 'none';
        face.style.display = 'block';
        const u = fullUrl(w.face_url);
        if (face.dataset.src !== u) { face.src = u; face.dataset.src = u; }
        face.play().catch(() => {});
      } else {
        face.pause();
        face.style.display = 'none';
        charWrap.style.display = 'block';
        const u = fullUrl(w.char_url);
        if (charImg.dataset.src !== u) { charImg.src = u; charImg.dataset.src = u; }
        $('studioWipeMouthEl').style.display = w.mouth_overlay === false ? 'none' : 'block';
      }
    }

    bindWipeDrag() {
      const box = $('studioWipePreview');
      const stage = $('editorLiveCutStage');
      if (!box || !stage) return;
      let drag = false;
      box.addEventListener('pointerdown', (e) => { drag = true; box.setPointerCapture(e.pointerId); e.preventDefault(); });
      box.addEventListener('pointerup', () => { drag = false; });
      box.addEventListener('pointermove', (e) => {
        if (!drag || !this.st?.studio) return;
        const r = stage.getBoundingClientRect();
        if (r.width <= 0) return;
        const x = Math.round(Math.min(92, Math.max(10, ((e.clientX - r.left) / r.width) * 100)));
        const y = Math.round(Math.min(92, Math.max(10, ((e.clientY - r.top) / r.height) * 100)));
        const w = this.st.studio.wipe;
        w.x_pct = x; w.y_pct = y;
        $('studioWipeX').value = x; $('studioWipeY').value = y;
        this.updateWipeLabels();
        this.updateWipePreview();
      });
    }

    startPreviewLoop() {
      if (this.raf) return;
      const tick = () => {
        this.raf = requestAnimationFrame(tick);
        const modal = $('proVideoEditorModal');
        if (!modal || modal.style.display === 'none' || !this.st?.studio) return;
        const w = this.st.studio.wipe;
        if (!w.enabled || w.mode !== 'character') return;
        const audio = $('editorCutAudioEl');
        const img = $('studioWipeCharImg');
        const mouth = $('studioWipeMouthEl');
        if (!img || !mouth) return;
        let a = 0;
        const cut = this.app.getActiveEditorCut();
        if (audio && !audio.paused && cut?.audio_url) {
          const env = this.envCache.get(fullUrl(cut.audio_url).split('?')[0]);
          if (env) {
            const idx = Math.min(env.rms.length - 1, Math.floor(audio.currentTime / env.step));
            let v = 0;
            for (let k = 0; k < 5; k++) v = Math.max(v, env.rms[Math.max(0, idx - k)] || 0);
            a = Math.min(1, v / 0.18);
          } else {
            a = 0.5 + 0.5 * Math.sin(performance.now() / 70);
            this.getAudioBuffer(cut).catch(() => {});
          }
        }
        const t = performance.now() / 1000;
        const bob = Math.sin(t * 2 * Math.PI * 1.4) * 1.6;
        img.style.transform = `translateY(${bob}px) scale(${1 + 0.035 * a})`;
        mouth.style.height = `${2 + 7.5 * a}%`;
      };
      this.raf = requestAnimationFrame(tick);
    }

    // ------------------------------------------------------------- telops
    splitCards(text, maxChars = 13) {
      const sentences = String(text || '').split(/(?<=[。！？!?])|\n/).map((x) => x.trim()).filter(Boolean);
      const cards = [];
      sentences.forEach((snt) => {
        for (let i = 0; i < snt.length; i += maxChars) cards.push(snt.slice(i, i + maxChars));
      });
      return cards;
    }

    autoTelops() {
      const s = this.ensure();
      if (!s) return this.toast('編集スタジオを開いてから実行してください', 'warning');
      const out = [];
      this.timeline().filter((x) => x.enabled).forEach(({ sc, start, dur }) => {
        const cards = this.splitCards(sc.telop_text ?? sc.narration ?? '');
        if (!cards.length) return;
        const totalChars = cards.reduce((a, c) => a + c.length, 0) || 1;
        let cur = start;
        cards.forEach((c, k) => {
          const d = k === cards.length - 1 ? start + dur - cur : dur * (c.length / totalChars);
          out.push({
            id: `tl_${Date.now()}_${out.length}`, text: c, start: +cur.toFixed(2), end: +(cur + d).toFixed(2),
            size: parseInt(sc.telop_scale ?? 100, 10), color: STYLE_COLORS[sc.telop_style] || '#FFE600',
            font: sc.telop_font || this.st.telop_font || 'DelaGothicOne', y_pct: parseInt(sc.telop_y_pct ?? 76, 10)
          });
          cur += d;
        });
      });
      s.telops = out;
      s.telops_override = out.length > 0;
      $('studioTelopsOverride').checked = s.telops_override;
      this.renderTelopList();
      this.renderExtraTracks();
      this.toast(out.length ? `テロップを${out.length}枚自動配置しました` : '配置できるテロップがありません', out.length ? 'success' : 'info');
    }

    addTelop() {
      const s = this.ensure();
      if (!s) return;
      const total = this.total();
      const start = Math.min(total - 1, 0);
      s.telops.push({ id: `tl_${Date.now()}`, text: '新しいテロップ', start, end: Math.min(total, start + 2), size: 100, color: '#FFE600', font: this.st.telop_font || 'DelaGothicOne', y_pct: 76 });
      this.renderTelopList();
      this.renderExtraTracks();
    }

    renderTelopList() {
      const box = $('studioTelopList');
      if (!box || !this.st?.studio) return;
      const esc = (t) => this.app._escapeHtml(String(t ?? ''));
      box.innerHTML = this.st.studio.telops.map((t, i) => `
        <div class="studio-list-row" data-i="${i}">
          <input type="text" class="form-input" data-f="text" value="${esc(t.text)}">
          <input type="color" data-f="color" value="${esc(t.color || '#FFE600')}" title="文字色" style="width:30px;height:26px;padding:0;border:none;background:none;">
          <label>サイズ%<input type="number" class="form-input" data-f="size" min="50" max="180" step="5" value="${t.size}"></label>
          <label>開始<input type="number" class="form-input" data-f="start" min="0" step="0.1" value="${t.start}"></label>
          <label>終了<input type="number" class="form-input" data-f="end" min="0" step="0.1" value="${t.end}"></label>
          <button type="button" class="btn btn-outline" data-f="del" style="padding:2px 8px;font-size:0.7rem;border-color:#ef4444;color:#f87171;">削除</button>
        </div>`).join('') || '<div style="font-size:0.74rem;color:#94a3b8;">テロップクリップは未配置です</div>';
      box.querySelectorAll('.studio-list-row').forEach((row) => {
        const i = parseInt(row.dataset.i, 10);
        row.querySelectorAll('[data-f]').forEach((el) => {
          const f = el.dataset.f;
          el.addEventListener(f === 'del' ? 'click' : 'input', () => {
            const arr = this.st.studio.telops;
            if (f === 'del') { arr.splice(i, 1); this.renderTelopList(); }
            else if (f === 'text' || f === 'color') arr[i][f] = el.value;
            else arr[i][f] = parseFloat(el.value) || 0;
            this.renderExtraTracks();
          });
        });
      });
    }

    // ---------------------------------------------------------------- BGM
    toggleBgmMute() {
      if (!this.ensure()) return;
      this.st.studio.bgm_muted = !this.st.studio.bgm_muted;
      this.syncBgm();
      this.renderExtraTracks();
    }

    async uploadBgm(e) {
      const file = e.target.files?.[0];
      e.target.value = '';
      if (!file || !this.ensure()) return;
      try {
        const data = await this.uploadAsset('bgm', file);
        const sel = $('editorGlobalBgmSelect');
        if (sel) {
          const opt = document.createElement('option');
          opt.value = data.bgm_choice;
          opt.textContent = `手持ち音源: ${file.name}`;
          sel.appendChild(opt);
          sel.value = data.bgm_choice;
        }
        this.st.bgm_choice = data.bgm_choice;
        this.st.studio.bgm_muted = false;
        this.syncBgm();
        this.renderExtraTracks();
        this.toast('BGMを手持ち音源に差し替えました', 'success');
      } catch (err) {
        this.toast('BGM差し替えエラー: ' + err.message, 'error');
      }
    }

    // ----------------------------------------------------- timeline tracks
    renderExtraTracks() {
      const host = $('studioExtraTracks');
      if (!host || !this.st?.studio) return;
      const s = this.st.studio;
      const total = this.total();
      const pos = (a, b) => `left:${(Math.max(0, a) / total) * 100}%;width:${Math.max(0.8, ((b - a) / total) * 100)}%;`;
      const esc = (t) => this.app._escapeHtml(String(t ?? ''));
      const broll = s.broll.filter((b) => b.enabled !== false)
        .map((b) => `<span class="studio-chip broll" style="${pos(b.start, b.start + b.duration)}" title="B-roll: ${esc(b.keyword)}">${esc(b.keyword)}</span>`).join('');
      const telop = s.telops
        .map((t) => `<span class="studio-chip telop" contenteditable="true" spellcheck="false" data-tid="${esc(t.id)}" style="${pos(t.start, t.end)}" title="クリックして直接編集">${esc(t.text)}</span>`).join('');
      const w = s.wipe;
      const wipe = w.enabled ? `<span class="studio-chip wipe" style="left:0;width:100%;">${w.mode === 'face' ? '実写顔ワイプ' : 'トーキングキャラ'} / ${w.shape === 'rounded' ? '角丸' : '円形'} ${w.size_pct}%</span>` : '';
      const bsel = $('editorGlobalBgmSelect');
      const bname = bsel && bsel.selectedOptions[0] ? bsel.selectedOptions[0].textContent : (this.st.bgm_choice || 'BGM');
      const pct = Math.round((parseFloat(this.st.bgm_volume ?? 0.15)) * 100);
      const bgm = `<span class="studio-chip bgm ${s.bgm_muted ? 'muted' : ''}" style="left:0;width:100%;">${esc(bname)} (${pct}%)</span>`;
      host.innerHTML = `
        <div class="studio-track-row"><span class="studio-track-label">B-ROLL</span><div class="studio-track-lane">${broll}</div></div>
        <div class="studio-track-row"><span class="studio-track-label">TELOP CLIP</span><div class="studio-track-lane">${telop}</div></div>
        <div class="studio-track-row"><span class="studio-track-label">WIPE</span><div class="studio-track-lane">${wipe}</div></div>
        <div class="studio-track-row"><span class="studio-track-label">BGM</span><div class="studio-track-lane">${bgm}</div>
          <span class="studio-bgm-ctrl">
            <button type="button" class="btn btn-outline" id="studioTrackMute" style="padding:2px 8px;font-size:0.68rem;">${s.bgm_muted ? '解除' : 'ミュート'}</button>
            <input type="range" id="studioTrackVol" class="form-range" min="0" max="100" value="${pct}" style="width:90px;">
          </span></div>`;
      host.querySelectorAll('.studio-chip.telop').forEach((chip) => {
        chip.addEventListener('input', () => {
          const t = s.telops.find((x) => x.id === chip.dataset.tid);
          if (!t) return;
          t.text = chip.textContent;
          const row = $('studioTelopList')?.querySelectorAll('.studio-list-row')[s.telops.indexOf(t)];
          const inp = row?.querySelector('[data-f="text"]');
          if (inp) inp.value = t.text;
        });
      });
      $('studioTrackMute')?.addEventListener('click', () => this.toggleBgmMute());
      $('studioTrackVol')?.addEventListener('input', (e) => {
        this.st.bgm_volume = parseInt(e.target.value, 10) / 100;
        this.syncBgm();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.appController) window.studioPro = new StudioPro(window.appController);
  });
})();
