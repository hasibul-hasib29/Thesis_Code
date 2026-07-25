"""
======================================================================
 QVSC — ICCIT 2026 PATCH SET
======================================================================
 Every block below is a self-contained notebook cell. Paste them where
 indicated. Blocks are numbered in EXECUTION ORDER — do not reorder,
 because later blocks depend on artifacts written by earlier ones.

 ORDER OF OPERATIONS
 -------------------
   P0  fec_module.py          RS_PARITY 32 -> 64          (edit file)
   P1  e91_sha3.ipynb         num_singlets 500 -> 5000    (edit call)
   P2  Module2                re-encode FEC payload       (re-run cell)
   P3  Module4/5/6            re-run end to end           (no code change)
   P4  Module7 Section 3      patch run_pipeline_once     (add 6 lines)
   P5  Module7 Section 11     capacity — REPLACE cell
   P6  Module7 Section 10     PSNR/SSIM figure — REPLACE cell
   P7  Module7 Section 10     FEC headroom figure — REPLACE cell
   P8  Module7 (new section)  multi-video sweep
   P9  Module7 (new section)  steganalysis
   P10 Module7 (new section)  ablations + LSB baseline
======================================================================
"""

# =====================================================================
# P0 — fec_module.py  (EDIT THE FILE, not a notebook cell)
# =====================================================================
# WHY: RS(255,223) corrects t = 16 byte-errors per codeword. A byte is
# wrong if ANY of its 8 bits flipped, so the 16/255 = 6.27% BYTE budget
# corresponds to only 1-(1-16/255)^(1/8) = 0.81% BIT BER. QP=28 sits at
# 0.63% bit BER — under the mean threshold, but per-codeword variance
# still killed 28 of 334 codewords. Doubling parity to 64 (t = 32) moves
# the cliff to 1.66% bit BER, which clears QP=28 with real margin.
#
# COST: payload expands 255/191 = 1.335x instead of 255/223 = 1.143x.
# Your capacity utilisation goes from 17% to 20% of 497,247 B. Free.
#
# Change these two lines in fec_module.py:
#
#     RS_PARITY = 64          # was 32
#     RS_K      = RS_N - RS_PARITY   # 191 (unchanged expression)
#
# Then restart every kernel — fec_module is imported at module scope and
# Python will otherwise keep the old RSCodec object cached.


# =====================================================================
# P1 — e91_sha3.ipynb, final execution cell
# =====================================================================
# WHY: CHSH uses only the 4 mismatched basis pairs (A1B1, A1B3, A3B1,
# A3B3) = 4/9 of all pairs. At N=500 that is ~222 pairs spread over four
# correlators, ~55 each. Standard error per correlator ~ 1/sqrt(55) =
# 0.135, and S sums four of them, so sigma_S ~ 0.27. Your |S| = 2.090 is
# a 2.7-sigma downward fluctuation from 2.828 — not a bug, but it reads
# like one, and it sits uncomfortably close to the classical bound of 2.
# N=5000 gives sigma_S ~ 0.085, so you should land at 2.83 +/- 0.09.
#
# Replace both calls:

# key_result = generate_quantum_key(num_singlets=5000, verbose=True)
# eve_result = run_eve_simulation(num_singlets=5000)

# Report it in the paper as: |S| = 2.83 +/- 0.09 (N = 5000 pairs),
# vs |S| = 1.34 under an intercept-resend attack. Quote the uncertainty.


# =====================================================================
# P2 — Module2, final FEC cell (re-run as-is after P0)
# =====================================================================
# No code change needed — but you MUST re-run it so fec_payload.bin is
# rebuilt with the new parity. Expected new numbers:
#     data_bytes 74449 -> codewords 390 -> fec_bytes 99450 (was 85170)
#     fec_bits 795600 (was 681360)
# Frames consumed will rise from 167 to roughly 195 of 425. Fine.
#
# import fec_module as fec
# open('fec_payload.bin','wb').write(fec.fec_encode(ciphertext))
# print(fec.fec_overhead(len(ciphertext)))
#
# NOTE ON REPORTING: fec_overhead()['redundancy_pct'] returns
# 100*RS_PARITY/RS_N = 25.1%, which is parity as a fraction of the
# CODEWORD. The payload EXPANSION is RS_N/RS_K = 1.335x = 33.5% added.
# Pick one definition and use it consistently in the paper. I would
# quote expansion, since that is what costs you capacity.


# =====================================================================
# P4 — Module7 Section 3: patch run_pipeline_once()
# =====================================================================
# WHY: your current avg_psnr/avg_ssim compare cover vs stego BEFORE
# compression, so they are identical (49.20 / 0.9974) at every QP. The
# figure titled "Imperceptibility vs Compression" is therefore flat by
# construction. We add a second measurement — cover vs DECODED stego —
# which is what a warden actually sees and which does vary with QP.
#
# Find this line inside run_pipeline_once (section 5, "Decode compressed
# video and extract"):
#
#     recv_frames, _, _, _ = extract_video_frames(comp_path)
#
# and insert the block below IMMEDIATELY AFTER it.

# ---------------- INSERT START ----------------
"""
    # ── 5b. Post-compression imperceptibility (what a warden sees) ────
    #  The pre-compression PSNR/SSIM above isolate the embedding
    #  distortion alone. These measure cover vs the DECODED stego frame,
    #  i.e. embedding distortion PLUS codec distortion. SSIM is costly,
    #  so we sample every 10th embedded frame; PSNR is cheap enough to
    #  run on all of them.
    post_psnr_list, post_ssim_list = [], []
    n_common = min(len(cover_frames), len(recv_frames), len(bits_per_frame))
    for i in range(n_common):
        if bits_per_frame[i] == 0:
            continue
        post_psnr_list.append(calculate_psnr(cover_frames[i], recv_frames[i]))
        if i % 10 == 0:
            post_ssim_list.append(calculate_ssim(cover_frames[i], recv_frames[i]))
    post_psnr = float(np.mean(post_psnr_list)) if post_psnr_list else float('nan')
    post_ssim = float(np.mean(post_ssim_list)) if post_ssim_list else float('nan')
"""
# ---------------- INSERT END ------------------
#
# Then add these two keys to the SUCCESS return dict at the end of the
# function (next to 'avg_psnr'):
#
#     'post_psnr':        post_psnr,
#     'post_ssim':        post_ssim,
#
# And add them to the two EARLY-RETURN dicts as None so the DataFrame
# stays rectangular:
#
#     'post_psnr': None, 'post_ssim': None,
#
# Finally, in the Section 9 aggregation cell, add to each row dict:
#
#     'post_psnr_db': r.get('post_psnr'),
#     'post_ssim':    r.get('post_ssim'),


# =====================================================================
# P5 — Module7 Section 11: capacity  (REPLACE THE WHOLE CELL)
# =====================================================================
# WHY THE OLD CELL WAS WRONG: it called detect_roi_blocks(cover_frames[0])
# and multiplied by len(cover_frames). Frame 0 of your clip is the hazy
# mountain shot with 254 ROI blocks — a pathological outlier. Frame 212
# has 10,394. Module 3 already measured the truth: 3,977,980 ROI blocks
# total = 497,247 bytes. The old figure understated capacity by ~37x and
# therefore drew your 85 KB payload ABOVE the capacity curve, which is
# self-refuting since the pipeline demonstrably embedded it.
#
# THE FIX: sum over EVERY frame. The naive way is too slow (6 thresholds
# x 425 frames x 32,400 blocks of pure-Python looping). So we compute the
# per-block edge density ONCE per frame with a vectorised reshape, then
# threshold that same density array at all six levels. One Canny pass per
# frame instead of six, and no Python inner loop at all.

CELL_P5 = r'''
# ── Capacity vs edge_threshold — measured over ALL frames ────────────
# detect_roi_blocks() decides a block is ROI when its dilated-edge
# density exceeds edge_threshold. That density is the same array for
# every threshold, so we compute it once per frame and reuse it. This
# is mathematically identical to calling detect_roi_blocks() six times
# per frame, just ~50x faster.

def block_edge_density(frame_bgr, block_size=8, canny_low=50, canny_high=150,
                       blur_sigma=1.0, dilate_iterations=2):
    """Return a (blocks_y, blocks_x) float array of edge density per block.
    Pipeline is byte-for-byte identical to detect_roi_blocks() up to the
    final comparison, so thresholding this reproduces that mask exactly."""
    ycrcb     = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
    y_blurred = cv2.GaussianBlur(ycrcb[:, :, 0], (5, 5), blur_sigma)
    edges     = cv2.Canny(y_blurred, canny_low, canny_high)
    kernel    = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    ed        = cv2.dilate(edges, kernel, iterations=dilate_iterations)

    h, w   = ed.shape
    by, bx = h // block_size, w // block_size
    # (by, bs, bx, bs) -> mean over the two intra-block axes
    tiles = (ed[:by * block_size, :bx * block_size] > 0).reshape(
        by, block_size, bx, block_size)
    return tiles.mean(axis=(1, 3))


edge_thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]

print("Computing per-block edge density for all frames...")
densities = [block_edge_density(f, BLOCK_SIZE) for f in cover_frames]
print(f"  {len(densities)} frames processed.")

capacity_data = []
for th in edge_thresholds:
    # Total ROI blocks across the WHOLE video, not frame 0 extrapolated
    total_blocks = int(sum(int((d > th).sum()) for d in densities))
    per_frame    = [int((d > th).sum()) for d in densities]

    capacity_data.append({
        'edge_threshold':   th,
        'roi_blocks_total': total_blocks,
        'roi_blocks_mean':  float(np.mean(per_frame)),
        'roi_blocks_min':   int(np.min(per_frame)),
        'roi_blocks_max':   int(np.max(per_frame)),
        'bits_per_video':   total_blocks,          # 1 bit per ROI block
        'bytes_per_video':  total_blocks // 8,
    })
    print(f"  threshold={th:.2f} -> {total_blocks:9,d} ROI blocks total "
          f"(mean {np.mean(per_frame):8.1f}/frame, "
          f"range {np.min(per_frame)}-{np.max(per_frame)}) "
          f"= {total_blocks // 8:8,d} B")

cap_df = pd.DataFrame(capacity_data)

# ── Plot: capacity vs threshold, with utilisation shown honestly ──────
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(cap_df['edge_threshold'], cap_df['bytes_per_video'] / 1024,
        'o-', linewidth=2, markersize=8, color='teal',
        label='Capacity (all frames)')

payload_kb = len(ciphertext_blob) / 1024
ax.axhline(payload_kb, color='crimson', linestyle=':', linewidth=2,
           label=f'FEC-protected payload ({payload_kb:.1f} KB)')
ax.axvline(0.30, color='gray', linestyle='--', alpha=0.6,
           label='Operating point (0.30)')

# Annotate utilisation at the operating point — this is the number a
# reviewer wants: how much headroom does the scheme actually have?
op = cap_df[cap_df['edge_threshold'] == 0.30].iloc[0]
util = 100 * len(ciphertext_blob) / op['bytes_per_video']
ax.annotate(f'{util:.1f}% utilised',
            xy=(0.30, op['bytes_per_video'] / 1024),
            xytext=(0.36, op['bytes_per_video'] / 1024 * 0.75),
            arrowprops=dict(arrowstyle='->', color='black', alpha=0.6),
            fontsize=10)

ax.set_xlabel('ROI edge-density threshold')
ax.set_ylabel('Payload capacity (KB)')
ax.set_title(f'Embedding Capacity vs ROI Threshold '
             f'({len(cover_frames)} frames @ {w}x{h})', fontsize=12)
ax.grid(True, alpha=0.3)
ax.legend()
plt.tight_layout()
plt.savefig(FIG_CAPACITY, dpi=300, bbox_inches='tight')
plt.show()

print(f"\n  Operating point (0.30): {op['bytes_per_video']:,} B capacity, "
      f"{len(ciphertext_blob):,} B payload = {util:.1f}% utilised")
print(f"  Cross-check vs Module 3 total_roi_blocks: expect 3,977,980")
print(f"  Saved: {FIG_CAPACITY}")
'''


# =====================================================================
# P6 — Module7 Section 10 Figure 1: PSNR/SSIM  (REPLACE THE WHOLE CELL)
# =====================================================================
# WHY: the old figure plotted pre-compression PSNR against QP and got a
# perfectly horizontal line, because compression is not in that metric.
# A reviewer sees a flat line on an axis labelled "vs Compression" and
# concludes either that the experiment is broken or that the axis is a
# lie. Requires the P4 patch to have run first.

CELL_P6 = r'''
# ── Figure 1: Imperceptibility — embedding vs embedding+codec ────────
# Two curves that answer two different questions:
#   Pre-compression  = distortion caused by DCT-QIM alone. Flat by
#                      construction (embedding does not know about QP);
#                      we plot it so the flatness is EXPLAINED, not hidden.
#   Post-compression = cover vs decoded stego, i.e. what a warden or
#                      viewer actually receives. Falls with QP, as it must.
if qp_results:
    fig, ax1 = plt.subplots(figsize=(8, 5))

    ok    = [r for r in qp_results if r.get('avg_psnr') is not None]
    qps   = [r['qp']        for r in ok]
    pre_p = [r['avg_psnr']  for r in ok]
    pst_p = [r.get('post_psnr', np.nan) for r in ok]
    pre_s = [r['avg_ssim']  for r in ok]
    pst_s = [r.get('post_ssim', np.nan) for r in ok]

    c1 = 'tab:blue'
    ax1.set_xlabel('H.264 QP (higher = stronger compression)')
    ax1.set_ylabel('PSNR (dB)', color=c1)
    ax1.plot(qps, pre_p, 'o--', color=c1, linewidth=2, markersize=8,
             alpha=0.55, label='PSNR: embedding only (cover vs stego)')
    ax1.plot(qps, pst_p, 'o-', color=c1, linewidth=2, markersize=8,
             label='PSNR: embedding + codec (cover vs decoded)')
    ax1.axhline(35, color=c1, linestyle=':', alpha=0.5)
    ax1.tick_params(axis='y', labelcolor=c1)
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    c2 = 'tab:red'
    ax2.set_ylabel('SSIM', color=c2)
    ax2.plot(qps, pre_s, 's--', color=c2, linewidth=2, markersize=7,
             alpha=0.55, label='SSIM: embedding only')
    ax2.plot(qps, pst_s, 's-', color=c2, linewidth=2, markersize=7,
             label='SSIM: embedding + codec')
    ax2.axhline(0.95, color=c2, linestyle=':', alpha=0.5)
    ax2.tick_params(axis='y', labelcolor=c2)

    # One merged legend, placed out of the way of both curve families
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc='lower left', fontsize=8, framealpha=0.9)

    plt.title(f'Imperceptibility: embedding distortion vs total distortion '
              f'(Delta={QIM_DELTA})', fontsize=11)
    fig.tight_layout()
    plt.savefig(FIG_PSNR_SSIM, dpi=300, bbox_inches='tight')
    plt.show()
    print(f"Saved: {FIG_PSNR_SSIM}")
'''


# =====================================================================
# P7 — Module7 Section 10 Figure 6: FEC headroom (REPLACE WHOLE CELL)
# =====================================================================
# WHY THE OLD FIGURE WAS WRONG: it drew a green band at 6.3% and plotted
# post-compression BIT error rate against it. But 6.3% = t/N = 16/255 is
# a BYTE-domain budget. Comparing bits to bytes across an 8x amplification
# made QP=28 (0.63% bit BER) look like it sat deep inside the safe band —
# yet it FAILED. Any reviewer who does the arithmetic rejects the paper.
#
# THE CORRECT THRESHOLD: a byte is corrupt if any of its 8 bits flipped,
# so byte_ER = 1 - (1 - bit_BER)^8. Setting byte_ER = t/N and solving:
#     bit_BER_cliff = 1 - (1 - t/N)^(1/8)
# For t=16: 0.81%.  For t=32 (after P0): 1.66%.
#
# BONUS: we overlay the predicted codeword-failure count from a binomial
# model. On your v3 data this predicted 42 failures at QP=28 against 28
# observed, and exact agreement (334/334) at QP=35 and Delta=30. Showing
# that your empirical results match an a-priori model is the single most
# persuasive thing you can put in a results section.

CELL_P7 = r'''
# ── Figure 6: FEC cliff in the correct (bit) domain ──────────────────
from scipy.stats import binom

if qp_results:
    ok    = [r for r in qp_results if r.get('post_ber') is not None]
    qps   = [r['qp']       for r in ok]
    bers  = [r['post_ber'] for r in ok]
    dec   = [r['decryption_ok'] for r in ok]
    fails = [r.get('fec_fails') for r in ok]

    t = fec.RS_PARITY // 2                       # correctable bytes / codeword
    # Invert byte_ER = 1-(1-bit_BER)^8 at byte_ER = t/N
    cliff_pct = (1.0 - (1.0 - t / fec.RS_N) ** (1.0 / 8.0)) * 100.0

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.axhspan(1e-4, cliff_pct, color='green', alpha=0.07)
    ax.axhline(cliff_pct, color='green', linestyle='--', linewidth=2,
               label=(f'RS({fec.RS_N},{fec.RS_N - fec.RS_PARITY}) cliff = '
                      f'{cliff_pct:.2f}% bit BER\n'
                      f'(t={t} bytes/codeword, '
                      f'byte ER = 1-(1-BER)$^8$)'))

    ax.plot(qps, bers, '-', color='gray', linewidth=1.5, zorder=1)
    for q, b, d, f in zip(qps, bers, dec, fails):
        ax.scatter([q], [b], s=150, zorder=3,
                   color=('green' if d else 'crimson'))
        ax.annotate(f"{'PASS' if d else 'FAIL'}\nRS fail={f}",
                    (q, b), textcoords='offset points', xytext=(0, 14),
                    ha='center', fontsize=9, fontweight='bold',
                    color=('green' if d else 'crimson'))

    ax.set_yscale('log')
    ax.set_xlabel('H.264 QP')
    ax.set_ylabel('Post-compression bit error rate (%)')
    ax.set_title('FEC headroom: AEAD succeeds only below the RS cliff',
                 fontsize=12)
    ax.grid(True, alpha=0.3, which='both')
    ax.legend(loc='upper left', fontsize=9)
    plt.tight_layout()
    plt.savefig(FIG_FEC_HEADROOM, dpi=300, bbox_inches='tight')
    plt.show()

    # ── Predicted vs observed codeword failures (paper Table III) ────
    # Independent-bit-error model. A codeword of RS_N bytes fails when
    # more than t of its bytes are corrupt.
    ncw = int(np.ceil((len(ciphertext_blob) + 4) /
                      (fec.RS_N - fec.RS_PARITY)))
    print(f"\n  Model check — {ncw} codewords, t={t}, "
          f"cliff={cliff_pct:.2f}% bit BER\n")
    print(f"  {'QP':>4} {'bit BER%':>10} {'byte ER%':>10} "
          f"{'predicted':>10} {'observed':>9}")
    print("  " + "-" * 47)
    for q, b, f in zip(qps, bers, fails):
        pb   = b / 100.0
        pB   = 1.0 - (1.0 - pb) ** 8
        pred = (1.0 - binom.cdf(t, fec.RS_N, pB)) * ncw
        print(f"  {q:>4} {b:>10.4f} {pB*100:>10.3f} "
              f"{pred:>10.1f} {str(f):>9}")
    print(f"\n  Saved: {FIG_FEC_HEADROOM}")
'''


# =====================================================================
# P8 — NEW SECTION: multi-video evaluation
# =====================================================================
# WHY: one cover video is an anecdote, not an evaluation. Reviewers in
# Track 3 will name this. Your current clip is also unrepresentative —
# frame 0 has 254 ROI blocks while frame 212 has 10,394, a 40x swing
# within one video, which means single-video numbers carry no meaningful
# error bar.
#
# WHAT TO GET: 4 more clips, 1920x1080, >= 300 frames, royalty-free
# (Pexels / Pixabay / Videvo). Cover these regimes deliberately:
#     high-motion + high-texture   (crowd, traffic)
#     high-motion + low-texture    (sky, water, drone over sea)
#     static + high-texture        (foliage, brickwork, market stall)
#     static + low-texture         (interior wall, studio shot)
# Name them cover_video_2.mp4 ... cover_video_5.mp4 in the working dir.
#
# RUNTIME: 5 videos x 4 QP x ~300 s = about 100 minutes. Start it and
# write the Method section while it runs.

CELL_P8 = r'''
# ── Multi-video robustness evaluation ────────────────────────────────
# For each cover video we regenerate ROI masks from scratch (they are
# content-dependent), verify capacity, then run the full QP sweep. Any
# video with insufficient capacity is skipped loudly rather than
# silently truncating the payload — a truncated payload would fail the
# Poly1305 check and look like a robustness failure when it is not.

VIDEO_PATHS = [
    'cover_video.mp4',
    'cover_video_2.mp4',
    'cover_video_3.mp4',
    'cover_video_4.mp4',
    'cover_video_5.mp4',
]

multi_results = []

for vpath in VIDEO_PATHS:
    if not os.path.exists(vpath):
        print(f"  SKIP (not found): {vpath}")
        continue

    print(f"\n{'='*70}\n  VIDEO: {vpath}\n{'='*70}")
    v_frames, v_fps, v_w, v_h = extract_video_frames(vpath)
    v_masks = np.stack([detect_roi_blocks(f, BLOCK_SIZE) for f in v_frames])

    cap_bits = int(v_masks.sum())
    print(f"  {len(v_frames)} frames @ {v_w}x{v_h}, "
          f"capacity {cap_bits:,} bits ({cap_bits//8:,} B), "
          f"payload {len(payload_bits):,} bits")

    if cap_bits < len(payload_bits):
        print(f"  SKIP: capacity {cap_bits:,} < payload {len(payload_bits):,} bits. "
              f"Use a longer clip or lower EDGE_THRESHOLD for this video.")
        continue

    for qp in QP_VALUES:
        r = run_pipeline_once(v_frames, v_masks, payload_bits, ciphertext_blob,
                              key, qp=qp, delta=QIM_DELTA, coeff_pos=COEFF_POS,
                              block_size=BLOCK_SIZE, preset=H264_PRESET)
        r['video']        = os.path.basename(vpath)
        r['n_frames']     = len(v_frames)
        r['capacity_b']   = cap_bits // 8
        r['utilisation']  = 100.0 * len(ciphertext_blob) / (cap_bits // 8)
        multi_results.append(r)

        if r.get('error'):
            print(f"    QP={qp}: ERROR {r['error']}")
        else:
            print(f"    QP={qp}: PSNR={r['avg_psnr']:.2f} dB  "
                  f"BER={r['post_ber']:.4f}%  "
                  f"RSfail={r['fec_fails']}  "
                  f"{'PASS' if r['decryption_ok'] else 'FAIL'}")

# ── Aggregate: mean +/- std per QP across videos (paper Table II) ────
mv = pd.DataFrame([r for r in multi_results if not r.get('error')])
if not mv.empty:
    agg = mv.groupby('qp').agg(
        n_videos      = ('video',         'nunique'),
        psnr_mean     = ('avg_psnr',      'mean'),
        psnr_std      = ('avg_psnr',      'std'),
        ssim_mean     = ('avg_ssim',      'mean'),
        ber_mean      = ('post_ber',      'mean'),
        ber_std       = ('post_ber',      'std'),
        mask_mean     = ('mask_agreement','mean'),
        success_rate  = ('decryption_ok', 'mean'),
    ).reset_index()
    agg['success_rate'] *= 100
    print("\n" + "="*70)
    print("  MULTI-VIDEO SUMMARY (mean +/- std across videos)")
    print("="*70)
    print(agg.to_string(index=False))
    mv.to_csv('multivideo_results.csv', index=False)
    agg.to_csv('multivideo_summary.csv', index=False)
    print("\n  Saved: multivideo_results.csv, multivideo_summary.csv")

    # Figure: BER vs QP, one line per video + shaded spread
    fig, ax = plt.subplots(figsize=(8, 5))
    for vid, g in mv.groupby('video'):
        g = g.sort_values('qp')
        ax.plot(g['qp'], g['post_ber'], 'o-', alpha=0.6, linewidth=1.5,
                markersize=6, label=vid)
    a = agg.sort_values('qp')
    ax.plot(a['qp'], a['ber_mean'], 'k-', linewidth=3, label='mean', zorder=5)
    ax.fill_between(a['qp'], a['ber_mean'] - a['ber_std'].fillna(0),
                    a['ber_mean'] + a['ber_std'].fillna(0),
                    color='gray', alpha=0.2)
    ax.set_yscale('log')
    ax.set_xlabel('H.264 QP')
    ax.set_ylabel('Post-compression bit error rate (%)')
    ax.set_title('Robustness across cover videos', fontsize=12)
    ax.grid(True, alpha=0.3, which='both')
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig('figure_multivideo_ber.png', dpi=300, bbox_inches='tight')
    plt.show()
'''


# =====================================================================
# P9 — NEW SECTION: steganalysis
# =====================================================================
# WHY: this is the section whose absence a reviewer will name explicitly.
# PSNR 49 dB and SSIM 0.997 establish perceptual invisibility only. They
# say nothing about STATISTICAL detectability, which is the actual
# security property of a steganographic system.
#
# WHAT QIM LEAVES BEHIND: qim_embed_bit() forces the (2,2) coefficient
# to Delta*round(c/Delta) +/- Delta/4. Every embedded coefficient
# therefore lands on one of two cosets spaced Delta/2 apart, producing a
# comb in the histogram with teeth at 12.5, 37.5, 62.5, ... for Delta=50.
# Natural DCT coefficients are smooth and roughly Laplacian. That
# contrast is what a detector exploits.
#
# EXPECT TO FAIL THIS TEST. Report it anyway. An honest negative result
# with a named mechanism is worth far more than a missing section, and
# it converts directly into your strongest future-work item.
#
# Requires: pip install scikit-learn

CELL_P9 = r'''
# ── Steganalysis: is the QIM signature statistically detectable? ─────
from scipy.fft import dctn as _dctn
from scipy.stats import entropy, chisquare
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler

STEG_N_FRAMES = 150     # frames sampled per class; raise if time allows
HIST_BINS     = 64
HIST_RANGE    = (-200, 200)


def frame_c22(frame_bgr, mask, block_size=8, coeff_pos=(2, 2)):
    """Vectorised: return the (2,2) DCT coefficient of every ROI block.

    Reshaping to (by, bx, 8, 8) and calling dctn over the last two axes
    is exactly equivalent to the per-block apply_dct_2d() loop used in
    embedding, but runs in one BLAS-backed pass instead of ~10,000
    Python iterations per frame.
    """
    chan   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float64)
    by, bx = mask.shape
    tiles  = chan[:by * block_size, :bx * block_size].reshape(
        by, block_size, bx, block_size).transpose(0, 2, 1, 3)
    D = _dctn(tiles, type=2, norm='ortho', axes=(2, 3))
    u, v = coeff_pos
    return D[:, :, u, v][mask.astype(bool)]


def hist_feature(coeffs, bins=HIST_BINS, rng=HIST_RANGE):
    """Normalised histogram of coefficient values = the feature vector."""
    h, _ = np.histogram(coeffs, bins=bins, range=rng)
    return h / max(h.sum(), 1)


# ── 1. Build the cover / stego frame pair set ────────────────────────
# Cover frames come straight from the source video. Stego frames are the
# DECODED output of the full pipeline at the operating point (QP=23),
# so the detector faces exactly what a warden would intercept.
print("Building stego video at the operating point (QP=23)...")
_bit_idx, _stego, _bpf = 0, [], []
for f in cover_frames:
    if _bit_idx >= len(payload_bits):
        _stego.append(f.copy()); _bpf.append(0); continue
    s, _bit_idx, n = embed_in_frame(f, roi_masks[len(_stego)], payload_bits,
                                    _bit_idx, BLOCK_SIZE, COEFF_POS, QIM_DELTA)
    _stego.append(s); _bpf.append(n)

_raw, _cmp = '_steg_raw.avi', '_steg_cmp.mp4'
_wr = cv2.VideoWriter(_raw, cv2.VideoWriter_fourcc(*'MJPG'), 30.0, (w, h))
for s in _stego:
    _wr.write(s)
_wr.release()
compress_h264_ffmpeg(_raw, _cmp, qp=23, preset=H264_PRESET, intra_only=True)
stego_dec, _, _, _ = extract_video_frames(_cmp)

# Only frames that actually carry payload are informative
embedded_idx = [i for i, n in enumerate(_bpf)
                if n > 0 and i < len(stego_dec)][:STEG_N_FRAMES]
print(f"  {len(embedded_idx)} embedded frames available for analysis.")

# ── 2. Pooled coefficient distributions + divergence statistics ──────
cov_all = np.concatenate([frame_c22(cover_frames[i], roi_masks[i])
                          for i in embedded_idx])
stg_all = np.concatenate([frame_c22(stego_dec[i], roi_masks[i])
                          for i in embedded_idx])

p = hist_feature(cov_all) + 1e-12
q = hist_feature(stg_all) + 1e-12
kl = float(entropy(q, p))          # KL(stego || cover), nats

# Chi-square on raw counts, cover as the expected distribution
c_cnt, _ = np.histogram(cov_all, bins=HIST_BINS, range=HIST_RANGE)
s_cnt, _ = np.histogram(stg_all, bins=HIST_BINS, range=HIST_RANGE)
exp = c_cnt * (s_cnt.sum() / max(c_cnt.sum(), 1)) + 1e-9
chi2_stat = float(((s_cnt - exp) ** 2 / exp).sum())

print(f"\n  KL(stego || cover)  = {kl:.4f} nats")
print(f"  Chi-square statistic = {chi2_stat:,.1f} (dof = {HIST_BINS - 1})")

# ── 3. Supervised detector: per-frame histogram -> logistic regression ─
X = np.array([hist_feature(frame_c22(cover_frames[i], roi_masks[i]))
              for i in embedded_idx] +
             [hist_feature(frame_c22(stego_dec[i], roi_masks[i]))
              for i in embedded_idx])
y = np.array([0] * len(embedded_idx) + [1] * len(embedded_idx))

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3,
                                      random_state=42, stratify=y)
sc  = StandardScaler().fit(Xtr)
clf = LogisticRegression(max_iter=2000, C=1.0).fit(sc.transform(Xtr), ytr)
prob = clf.predict_proba(sc.transform(Xte))[:, 1]
auc  = roc_auc_score(yte, prob)
acc  = clf.score(sc.transform(Xte), yte)

print(f"\n  Detector AUC       = {auc:.4f}   (0.50 = undetectable)")
print(f"  Detector accuracy  = {acc*100:.1f}%  "
      f"({len(yte)} held-out frames)")

# ── 4. Figure: the comb signature + ROC ──────────────────────────────
fig, (axA, axB) = plt.subplots(1, 2, figsize=(12, 4.5))

ctr = np.linspace(HIST_RANGE[0], HIST_RANGE[1], HIST_BINS)
axA.plot(ctr, p, linewidth=1.8, label='Cover', color='steelblue')
axA.plot(ctr, q, linewidth=1.8, label='Stego (QP=23)', color='crimson',
         alpha=0.85)
# Mark where QIM forces coefficients to land: k*Delta +/- Delta/4
for k in range(-3, 4):
    for s in (+1, -1):
        axA.axvline(k * QIM_DELTA + s * QIM_DELTA / 4, color='gray',
                    linestyle=':', alpha=0.35, linewidth=0.8)
axA.set_xlabel(f'DCT coefficient {COEFF_POS} value')
axA.set_ylabel('Normalised frequency')
axA.set_title(f'QIM comb signature (Delta={QIM_DELTA}), '
              f'KL={kl:.3f} nats', fontsize=11)
axA.legend(); axA.grid(True, alpha=0.3)

fpr, tpr, _ = roc_curve(yte, prob)
axB.plot(fpr, tpr, linewidth=2.2, color='darkorange',
         label=f'Histogram detector (AUC = {auc:.3f})')
axB.plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Chance (AUC = 0.50)')
axB.set_xlabel('False positive rate')
axB.set_ylabel('True positive rate')
axB.set_title('Steganalysis ROC', fontsize=11)
axB.legend(loc='lower right'); axB.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('figure_steganalysis.png', dpi=300, bbox_inches='tight')
plt.show()

for _p in (_raw, _cmp):
    if os.path.exists(_p):
        os.remove(_p)

np.save('steganalysis_report.npy', {
    'kl_divergence': kl, 'chi2': chi2_stat,
    'auc': float(auc), 'accuracy': float(acc),
    'n_frames': len(embedded_idx), 'qp': 23, 'delta': QIM_DELTA,
})
print("\n  Saved: figure_steganalysis.png, steganalysis_report.npy")
'''


# =====================================================================
# P10 — NEW SECTION: ablations + naive baseline
# =====================================================================
# WHY: right now nothing in the paper shows that ROI selection or the FEC
# layer EARN their complexity, and nothing shows that "compression
# resilience" is a non-trivial property. Three cheap experiments fix all
# three gaps and give you a clean paper table.
#
#   A. ROI ON vs OFF  — embed in every block instead of edge-dense ones.
#                       Isolates what adaptive masking buys in PSNR.
#   B. FEC ON vs OFF  — feed raw ciphertext instead of the RS-protected
#                       blob. AEAD is all-or-nothing, so ANY residual bit
#                       error kills it. This is the experiment that proves
#                       FEC is architectural, not decorative.
#   C. Spatial LSB    — the standard naive baseline. It should be wiped
#                       out by H.264 (BER near 50%), which is precisely
#                       what makes your DCT-QIM result meaningful.

CELL_P10 = r'''
# ── Ablation A: adaptive ROI vs embed-everywhere ─────────────────────
# Same payload, same Delta, same QP. The only change is the mask: an
# all-ones mask embeds into flat regions too, where the eye is most
# sensitive to an isolated DCT perturbation.
print("Ablation A — ROI masking on/off (QP=23)")
abl = []

r_roi = run_pipeline_once(cover_frames, roi_masks, payload_bits,
                          ciphertext_blob, key, qp=23, delta=QIM_DELTA,
                          coeff_pos=COEFF_POS, block_size=BLOCK_SIZE,
                          preset=H264_PRESET)
abl.append({'config': 'Adaptive ROI (proposed)', **r_roi})

full_masks = np.ones_like(roi_masks)
r_full = run_pipeline_once(cover_frames, full_masks, payload_bits,
                           ciphertext_blob, key, qp=23, delta=QIM_DELTA,
                           coeff_pos=COEFF_POS, block_size=BLOCK_SIZE,
                           preset=H264_PRESET)
abl.append({'config': 'No ROI (all blocks)', **r_full})

for a in abl:
    print(f"  {a['config']:<26} PSNR={a['avg_psnr']:.2f} dB  "
          f"SSIM={a['avg_ssim']:.4f}  BER={a['post_ber']:.4f}%  "
          f"{'PASS' if a['decryption_ok'] else 'FAIL'}")


# ── Ablation B: with and without the FEC layer ───────────────────────
# We reuse the QP sweep BER numbers rather than re-embedding. Without
# FEC the recovered ciphertext must be bit-exact for Poly1305 to verify,
# so P(success) = (1 - BER)^n over the whole payload — astronomically
# small for any non-zero BER. This is the quantitative statement of
# "AEAD makes the channel all-or-nothing".
print("\nAblation B — FEC on/off")
raw_ct_bits = len(ciphertext_blob) * 8
print(f"  {'QP':>4} {'BER%':>9} {'P(success) no FEC':>20} {'with FEC':>10}")
print("  " + "-" * 47)
for r in qp_results:
    if r.get('post_ber') is None:
        continue
    pb = r['post_ber'] / 100.0
    p_nofec = (1 - pb) ** raw_ct_bits if pb > 0 else 1.0
    print(f"  {r['qp']:>4} {r['post_ber']:>9.4f} {p_nofec:>20.3e} "
          f"{'PASS' if r['decryption_ok'] else 'FAIL':>10}")
print("  Interpretation: without FEC the scheme succeeds only at BER")
print("  exactly 0. Every non-zero row above is a total loss.")


# ── Ablation C: spatial-domain LSB baseline ──────────────────────────
# The classical naive method: overwrite the least significant bit of Y
# pixels inside ROI blocks. H.264 requantisation destroys the LSB plane
# almost completely, so BER should approach 50% (i.e. chance).
def lsb_embed_frame(frame_bgr, mask, bits, bit_index, block_size=8):
    ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
    chan  = ycrcb[:, :, 0]
    by_n, bx_n = mask.shape
    n = 0
    for by in range(by_n):
        for bx in range(bx_n):
            if bit_index >= len(bits):
                break
            if mask[by, bx] == 0:
                continue
            # One bit per block, in the block's top-left pixel, so that
            # capacity matches DCT-QIM exactly and the comparison is fair
            y0, x0 = by * block_size, bx * block_size
            chan[y0, x0] = (chan[y0, x0] & 0xFE) | int(bits[bit_index])
            bit_index += 1; n += 1
        if bit_index >= len(bits):
            break
    ycrcb[:, :, 0] = chan
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR), bit_index, n


def lsb_extract_frame(frame_bgr, mask, n_bits, block_size=8):
    chan = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0]
    out, by_n, bx_n = [], *mask.shape
    for by in range(by_n):
        for bx in range(bx_n):
            if len(out) >= n_bits:
                break
            if mask[by, bx] == 0:
                continue
            out.append(int(chan[by * block_size, bx * block_size] & 1))
        if len(out) >= n_bits:
            break
    return out


print("\nAblation C — spatial LSB baseline (QP=23)")
_i, lsb_frames, lsb_bpf, psnrs = 0, [], [], []
for f in cover_frames:
    if _i >= len(payload_bits):
        lsb_frames.append(f.copy()); lsb_bpf.append(0); continue
    s, _i, n = lsb_embed_frame(f, roi_masks[len(lsb_frames)],
                               payload_bits, _i, BLOCK_SIZE)
    lsb_frames.append(s); lsb_bpf.append(n)
    if n > 0:
        psnrs.append(calculate_psnr(f, s))

_r, _c = '_lsb_raw.avi', '_lsb_cmp.mp4'
_wr = cv2.VideoWriter(_r, cv2.VideoWriter_fourcc(*'MJPG'), 30.0, (w, h))
for s in lsb_frames:
    _wr.write(s)
_wr.release()
compress_h264_ffmpeg(_r, _c, qp=23, preset=H264_PRESET, intra_only=True)
lsb_dec, _, _, _ = extract_video_frames(_c)

lb, left = [], len(payload_bits)
for i, fr in enumerate(lsb_dec):
    if left <= 0 or i >= len(lsb_bpf) or lsb_bpf[i] == 0:
        continue
    e = lsb_extract_frame(fr, roi_masks[i], lsb_bpf[i], BLOCK_SIZE)
    lb.extend(e); left -= len(e)
lb = np.array(lb[:len(payload_bits)], dtype=np.uint8)
lsb_ber = float(np.mean(lb != payload_bits[:len(lb)]) * 100)

print(f"  LSB baseline: PSNR={np.mean(psnrs):.2f} dB, "
      f"post-compression BER={lsb_ber:.2f}%")
print(f"  Proposed DCT-QIM at the same QP: "
      f"BER={qp_results[1]['post_ber']:.4f}%")

for _p in (_r, _c):
    if os.path.exists(_p):
        os.remove(_p)

pd.DataFrame(abl).to_csv('ablation_results.csv', index=False)
print("\n  Saved: ablation_results.csv")
'''

if __name__ == '__main__':
    import ast
    for name, src in [(k, v) for k, v in sorted(globals().items())
                      if k.startswith('CELL_')]:
        ast.parse(src)
        print(f"{name}: syntax OK ({len(src.splitlines())} lines)")
