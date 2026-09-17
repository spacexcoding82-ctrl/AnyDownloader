import { useEffect, useRef, useState } from 'react';
import { PiArrowDownBold, PiDownloadSimpleBold, PiLinkBold, PiGearSixBold, PiRocketLaunchDuotone, PiMonitorPlayDuotone, PiDevicesDuotone, PiShieldCheckDuotone, PiArrowRightBold, PiCheckBold, PiXBold, PiSpinnerGapBold, PiFilmSlateDuotone, PiWarningCircleBold, PiDotsThreeBold, PiPlayFill, PiListBold, PiCopySimpleBold } from 'react-icons/pi';
import { SiYoutube, SiInstagram, SiTiktok, SiFacebook, SiX, SiPinterest, SiVimeo } from 'react-icons/si';
import { api, bytes, duration } from './api';
import './viddl.css';
import './refinements.css';

const platforms = [
  { name: 'YouTube', icon: SiYoutube, className: 'youtube', example: 'https://www.youtube.com/watch?v=…' },
  { name: 'Instagram', icon: SiInstagram, className: 'instagram', example: 'https://www.instagram.com/reel/…' },
  { name: 'TikTok', icon: SiTiktok, className: 'tiktok', example: 'https://www.tiktok.com/@creator/video/…' },
  { name: 'Facebook', icon: SiFacebook, className: 'facebook', example: 'https://www.facebook.com/reel/…' },
  { name: 'Twitter / X', icon: SiX, className: 'twitter', example: 'https://x.com/creator/status/…' },
  { name: 'Pinterest', icon: SiPinterest, className: 'pinterest', example: 'https://www.pinterest.com/pin/…' },
  { name: 'Vimeo', icon: SiVimeo, className: 'vimeo', example: 'https://vimeo.com/…' },
];
const qualities = [[1080, 'Full HD'], [720, 'HD'], [480, 'SD'], [360, 'Standard'], [240, 'Data saver']];
const features = [
  [PiRocketLaunchDuotone, 'Fast Download', 'Paste a link and get straight to your video.'],
  [PiMonitorPlayDuotone, 'High Quality', 'Choose the quality you need, up to 1080p.'],
  [PiDevicesDuotone, 'Flexible Formats', 'Save as MP4 or WebM. No app to install.'],
  [PiShieldCheckDuotone, 'No Sign-up', 'Temporary files. No account required.'],
];
function BrandTile({ platform, floating = false }) {
  const Icon = platform.icon;
  return <span className={`brand-tile ${platform.className} ${floating ? 'floating-tile' : ''}`}><Icon aria-hidden="true" /></span>;
}
function AppDialog({ kind, onClose }) {
  const ref = useRef(null);
  useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} className="info-dialog" onCancel={onClose} onClick={e => { if (e.target === ref.current) onClose(); }}>
    <button className="icon-button dialog-close" onClick={onClose} aria-label="Close"><PiXBold /></button><span className="eyebrow">GOOD TO KNOW</span><h2>{kind}</h2>
    {kind === 'Privacy' ? <><p>No account is needed. A temporary session cookie keeps your download private to this browser.</p><p>Links and job details are held in server memory temporarily. Video files are deleted after the save finishes, or roughly 15 minutes after processing. Use Cancel to stop a job; closing the page does not stop it immediately.</p><p>Hashed IP addresses are used for limits for up to 24 hours. Hosting providers may keep access logs. Thumbnails load from the original platform.</p></> : <><p>Download videos you own or have permission to save. A public link does not automatically grant permission.</p><p>Only public, non-protected videos are supported. Availability depends on the platform, your region, and the video. Private content, login-required videos, playlists, live streams, and protected media are unavailable.</p><p>YouTube support is experimental. Its terms restrict downloads outside authorized features. Use the platform’s official download option when available.</p><p>The free service supports up to 1080p and 500 MB, with 10 processing requests per IP per 24 hours. Files can be saved once. Free hosting may sleep or reach traffic limits.</p></>}
    <button className="primary-button" onClick={onClose}>Got it <PiCheckBold /></button>
  </dialog>;
}
export function App() {
  const [url, setUrl] = useState(''), [info, setInfo] = useState(null), [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(false), [starting, setStarting] = useState(false), [error, setError] = useState('');
  const [job, setJob] = useState(null), [confirmed, setConfirmed] = useState(false), [saving, setSaving] = useState(false);
  const [menu, setMenu] = useState(false), [dialog, setDialog] = useState(null), [platformHint, setPlatformHint] = useState(null), [polling, setPolling] = useState(true);
  const input = useRef(null), analysis = useRef(null), version = useRef(0), session = useRef(null);
  const active = starting || ['queued', 'downloading', 'merging'].includes(job?.status);
  const choice = info?.formats.find(f => f.key === selected);
  async function ensureSession() {
    if (!session.current) session.current = api('/config').catch(e => { session.current = null; throw e; });
    return session.current;
  }
  useEffect(() => { ensureSession().catch(() => {}); return () => analysis.current?.abort(); }, []);
  useEffect(() => {
    if (!job?.job_id || !['queued', 'downloading', 'merging'].includes(job.status) || !polling) return;
    let stopped = false, timer, failures = 0;
    const controller = new AbortController();
    async function poll() {
      try {
        const next = await api(`/jobs/${job.job_id}`, { signal: controller.signal });
        if (stopped) return;
        failures = 0; setJob(next);
        if (next.status === 'failed') setError(next.error?.message || 'This video could not be downloaded.');
        if (['queued', 'downloading', 'merging'].includes(next.status)) timer = setTimeout(poll, 1200);
      } catch (e) {
        if (stopped) return;
        failures++;
        if (failures >= 3 || e.code === 'not_found') {
          setPolling(false);
          if (e.code === 'not_found') setJob(previous => ({ ...previous, status: 'failed' }));
          setError(e.code === 'not_found' ? e.message : 'Connection interrupted. Your video may still be processing. Reconnect to check its status.');
        }
        else timer = setTimeout(poll, 2500);
      }
    }
    poll(); return () => { stopped = true; clearTimeout(timer); controller.abort(); };
  }, [job?.job_id, job?.status, polling]);
  const focusInput = () => { setMenu(false); document.getElementById('download').scrollIntoView({ behavior: 'smooth', block: 'center' }); input.current.focus({ preventScroll: true }); };
  async function inspect(e) {
    e.preventDefault(); if (active) return;
    let parsed;
    try { parsed = new URL(url.trim()); } catch { setError('Paste a complete video link, starting with https://'); input.current.focus(); return; }
    if (!['http:', 'https:'].includes(parsed.protocol)) { setError('Use an http or https video link.'); return; }
    analysis.current?.abort(); const controller = new AbortController(); analysis.current = controller;
    const current = ++version.current;
    setLoading(true); setError(''); setInfo(null); setJob(null); setSaving(false); setConfirmed(false);
    const timer = setTimeout(() => controller.abort(), 70000);
    try {
      await ensureSession();
      const data = await api('/inspect', { method: 'POST', body: JSON.stringify({ url: url.trim() }), signal: controller.signal });
      if (current === version.current) { setInfo(data); setSelected(data.formats[0].key); }
    } catch (e) { if (current === version.current) setError(e.name === 'AbortError' ? 'This request took too long. The service may be waking up; please try again.' : e.message); }
    finally { clearTimeout(timer); if (current === version.current) setLoading(false); }
  }
  async function startDownload() {
    if (!choice || !confirmed || starting) return;
    setStarting(true); setError(''); setSaving(false); setPolling(true);
    try { setJob(await api('/download', { method: 'POST', body: JSON.stringify({ inspection_id: info.inspection_id, format_key: selected, rights_confirmed: confirmed }) })); }
    catch (e) { setError(e.message); } finally { setStarting(false); }
  }
  async function cancel() {
    try { await api(`/jobs/${job.job_id}`, { method: 'DELETE', body: '{}' }); setJob(null); setError(''); setPolling(true); }
    catch (e) { setError(e.message); }
  }
  function resetUrl(value) {
    if (active) return;
    analysis.current?.abort(); version.current++;
    setUrl(value); setInfo(null); setJob(null); setLoading(false); setError(''); setSaving(false);
  }
  async function paste() {
    try { resetUrl(await navigator.clipboard.readText()); input.current.focus(); }
    catch { setError('Paste your copied video link using Ctrl+V or a long press.'); input.current.focus(); }
  }
  const statusLabel = { queued: 'You’re in the queue', downloading: 'Getting your video', merging: 'Putting the finishing touches on', ready: 'Your video is ready', saved: 'Video sent to your browser', failed: 'We couldn’t prepare this video', cancelled: 'Download cancelled' };
  return <>
    <a className="skip-link" href="#download">Skip to video downloader</a>
    <header className="site-header"><div className="header-inner">
      <a className="logo" href="#home" aria-label="VidDL home"><span className="logo-icon"><PiPlayFill /></span><span><strong>VidDL<span className="logo-dot">.</span></strong><small>All your videos. One place.</small></span></a>
      <nav className={menu ? 'nav-links is-open' : 'nav-links'} aria-label="Main navigation">{[['Home', 'home'], ['Supported Sites', 'platforms'], ['How It Works', 'how-it-works'], ['Features', 'features']].map(([label, id], i) => <a key={id} className={i === 0 ? 'active' : ''} href={`#${id}`} onClick={() => setMenu(false)}>{label}</a>)}</nav>
      <button className="header-cta" onClick={focusInput}><PiDownloadSimpleBold /> Start downloading</button><button className="icon-button mobile-menu" onClick={() => setMenu(!menu)} aria-label={menu ? 'Close navigation' : 'Open navigation'} aria-expanded={menu}>{menu ? <PiXBold /> : <PiListBold />}</button>
    </div></header>
    <main id="home">
      <section className="hero" aria-labelledby="hero-title">
        <div className="ambient-orb orb-left" /><div className="ambient-orb orb-right" />
        <div className="floating-platforms" aria-hidden="true">{[platforms[0], platforms[1], platforms[2], platforms[3], platforms[4], platforms[5]].map((p, i) => <div key={p.name} className={`floating-position float-${i}`}><BrandTile platform={p} floating /></div>)}</div>
        <div className="hero-content"><h1 id="hero-title">Download Videos<br />from <span>Any Platform</span></h1><p className="hero-subtitle">Paste the video URL · Choose quality · Download your video</p>
          <form className="download-form" id="download" onSubmit={inspect}>
            <span className="input-icon"><PiLinkBold /></span><label className="sr-only" htmlFor="video-url">Video link</label><input id="video-url" ref={input} type="text" inputMode="url" autoComplete="off" spellCheck="false" maxLength={2048} placeholder="Paste video URL here…" value={url} onChange={e => resetUrl(e.target.value)} disabled={active} aria-describedby="download-note" required />
            {!url && <button className="paste-button" type="button" onClick={paste} aria-label="Paste video link from clipboard"><PiCopySimpleBold /><span>Paste</span></button>}
            {url && !active && !loading && <button className="icon-button clear-button" type="button" onClick={() => resetUrl('')} aria-label="Clear video link"><PiXBold /></button>}
            <button className="primary-button analyze-button" type="submit" disabled={loading || active}>{loading ? <PiSpinnerGapBold className="spin" /> : <PiArrowDownBold />}<span>{loading ? 'Checking…' : 'Download'}</span></button>
          </form>
          <p className="input-note" id="download-note">YouTube, Instagram, TikTok, Pinterest & more.<span className="note-divider"> · </span><span>No sign-up needed.</span></p>
          {loading && <div className="loading-note" role="status"><PiSpinnerGapBold className="spin" /><span>Finding your video and its available qualities…<small>First request? The free service may take a moment to wake up.</small></span></div>}
          {error && <div className="error-message" role="alert"><PiWarningCircleBold /><span>{error}</span><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss message"><PiXBold /></button></div>}
          <section className={`quality-panel ${info ? 'has-video' : ''}`} aria-labelledby="quality-title" aria-busy={loading}>
            {info && <div className="video-preview"><div className="video-thumbnail"><PiFilmSlateDuotone />{info.thumbnail && <img src={info.thumbnail} alt="" referrerPolicy="no-referrer" onError={e => { e.currentTarget.hidden = true; }} />}{duration(info.duration) && <span>{duration(info.duration)}</span>}</div><div className="video-summary"><span className="eyebrow">{info.platform}</span><h2>{info.title}</h2><p><PiCheckBold /> Link checked · Choose how you’d like to save it</p></div></div>}
            <div className="quality-heading"><span className="quality-gear"><PiGearSixBold /></span><h2 id="quality-title">Choose Your Preferred Quality</h2>{info && <span className="format-count">{info.formats.length} options</span>}</div>
            <div className={`quality-grid ${info ? 'dynamic-grid' : ''}`}>{info ? info.formats.map(format => <button key={format.key} className={`quality-card ${selected === format.key ? 'selected' : ''}`} onClick={() => setSelected(format.key)} disabled={active || job?.status === 'ready'} aria-pressed={selected === format.key}>{selected === format.key && <span className="quality-check"><PiCheckBold /></span>}<strong>{format.label}</strong><span>{format.container.toUpperCase()}{format.fps > 30 ? ` · ${Math.round(format.fps)}fps` : ''}</span><small>{format.size_is_estimate && format.size_bytes ? '~' : ''}{bytes(format.size_bytes)}{!format.has_audio ? ' · No audio' : ''}</small></button>) : qualities.map(([height, caption], i) => <div key={height} className={`quality-card quality-placeholder ${i === 0 ? 'featured' : ''}`}><strong>{height}p</strong><span>{caption}</span>{i === 0 && <span className="free-tag">FREE</span>}</div>)}</div>
            {!info && <p className="quality-note">Available qualities appear after you paste a link.<span> Up to 1080p · 500 MB per video</span></p>}
            {info && !active && !['ready', 'saved'].includes(job?.status) && <div className="download-actions"><label className="rights-checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /><span>I own this video or have permission to download it.</span></label><button className="primary-button" onClick={startDownload} disabled={!confirmed || starting}><PiDownloadSimpleBold /> Download {choice?.label} {choice?.container.toUpperCase()}</button><p className="quality-note">Max. 500 MB · Files expire after 15 minutes · <button className="text-button" onClick={() => setDialog('Download terms')}>Download terms</button></p></div>}
            {job && <div className={`job-panel job-${job.status}`} aria-live="polite"><div className="job-title"><span>{active ? <PiSpinnerGapBold className="spin" /> : ['ready', 'saved'].includes(job.status) ? <PiCheckBold /> : <PiWarningCircleBold />}{statusLabel[job.status] || 'Preparing your video'}</span>{active && <button className="text-button" onClick={cancel}>Cancel</button>}</div>
              {active && <><div className={`progress-track ${job.progress == null ? 'indeterminate' : ''}`} role="progressbar" aria-label="Preparing video" aria-valuenow={job.progress ?? undefined} aria-valuemin={0} aria-valuemax={100}><div style={{ width: job.progress == null ? '35%' : `${job.progress}%` }} /></div><p>{job.status === 'queued' ? 'Another video is processing. Your download will start automatically.' : `${bytes(job.downloaded_bytes)}${job.progress ? ` · ${job.progress}%` : ''} · Keep this page open`}</p></>}
              {!polling && active && <button className="primary-button" onClick={() => { setPolling(true); setError(''); }}>Reconnect</button>}
              {job.status === 'ready' && <><p>{bytes(job.size_bytes)} · Ready to save. This link works once and expires in 15 minutes.</p><a className={`primary-button save-button ${saving ? 'is-saved' : ''}`} href={job.file_url} download onClick={e => { if (saving) e.preventDefault(); else setSaving(true); }} aria-disabled={saving}>{saving ? <PiCheckBold /> : <PiDownloadSimpleBold />}{saving ? 'Sent to your browser' : 'Save video to device'}</a>{saving && <p>Check your browser’s downloads. <button className="text-button" onClick={() => { setJob(null); setSaving(false); }}>Prepare another copy</button></p>}</>}
            </div>}
          </section>
        </div>
      </section>
      <section className="features page-width" id="features" aria-label="Why download with VidDL">{features.map(([Icon, title, copy], i) => <article className={`feature-card feature-${i}`} key={title}><span className="feature-icon"><Icon /></span><h3>{title}</h3><p>{copy}</p></article>)}</section>
      <section className="platform-section page-width" id="platforms"><div className="section-heading"><span className="eyebrow">ALL YOUR FAVORITES</span><h2>One place. So many platforms.</h2><p>From the reel you loved to the video worth keeping.</p></div><div className="platform-grid">{platforms.map(p => <button className={`platform-card ${platformHint?.name === p.name ? 'is-selected' : ''}`} key={p.name} onClick={() => setPlatformHint(platformHint?.name === p.name ? null : p)} aria-pressed={platformHint?.name === p.name}><BrandTile platform={p} /><span>{p.name}</span></button>)}<button className="platform-card" onClick={() => setPlatformHint({ name: 'More platforms', example: 'Paste a public video link to check support. Private, protected, live, and login-required videos are unavailable.' })}><span className="more-icon"><PiDotsThreeBold /></span><span>+ More</span></button></div>{platformHint && <div className="platform-detail"><div><strong>{platformHint.name}</strong><p>{platformHint.example}</p>{platformHint.name === 'YouTube' && <small>Experimental support. Platform restrictions apply.</small>}</div><button className="text-button" onClick={focusInput}>Try a link <PiArrowRightBold /></button></div>}<p className="platform-footnote">Public videos only. Availability and qualities vary by platform.</p></section>
      <section className="how-section page-width" id="how-it-works"><div className="section-heading"><h2>Three steps. That’s it.</h2><p>Less figuring things out. More saving what you love.</p></div><div className="steps">{[[PiLinkBold, 'Paste Video URL', 'Copy the link to a public video and paste it in the box above.'], [PiGearSixBold, 'Choose Your Quality', 'Pick an available resolution and format that works for you.'], [PiDownloadSimpleBold, 'Make It Yours', 'We’ll prepare your video. Save it straight to your device.']].map(([Icon, title, copy], i) => <div className="step" key={title}><span className="step-icon"><Icon /><small>{String(i + 1).padStart(2, '0')}</small></span>{i < 2 && <PiArrowRightBold className="step-arrow" />}<h3>{title}</h3><p>{copy}</p></div>)}</div></section>
      <section className="bottom-cta page-width"><div className="cta-icon"><PiDownloadSimpleBold /></div><div><h2>Found something worth keeping?</h2><p>Paste your link. We’ll take it from here.</p></div><button onClick={focusInput}>Let’s download <PiArrowRightBold /></button></section>
      <footer className="footer page-width"><a className="footer-brand" href="#home">VidDL<span>.</span></a><p>Your videos. Your way.</p><div><button onClick={() => setDialog('Privacy')}>Privacy</button><button onClick={() => setDialog('Download terms')}>Terms & limits</button><span>© {new Date().getFullYear()} VidDL</span></div></footer>
    </main>{dialog && <AppDialog kind={dialog} onClose={() => setDialog(null)} />}
  </>;
}
