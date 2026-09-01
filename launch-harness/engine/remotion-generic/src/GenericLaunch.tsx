import React from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

/**
 * Generic launch-video template — Category 3 (pure motion, no footage).
 *
 * Every product-specific value arrives through props. Nothing in this file is
 * tied to any particular product: no product name, no colour, no feature copy,
 * no timing belonging to one specific video.
 *
 * Three scenes, exactly:
 *   1. title   — product name + tagline
 *   2. feature — the feature list (+ optional screenshot)
 *   3. cta     — call to action
 *
 * Scene lengths are FRACTIONS of the total runtime, so the template works at
 * any durationInFrames without retuning.
 */
export type LaunchTemplateProps = {
  productName: string;
  accentColor: string;
  backgroundColor: string;
  featureList: string[];
  screenshotUrl?: string | null;
  tagline?: string;
  ctaText?: string;
  ctaUrl?: string;
};

const FONT =
  "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const TITLE_FRACTION = 0.3;
const FEATURE_FRACTION = 0.4;

/** Cross-dissolve length, in frames (12 @ 30fps = 0.40s). */
const XF_FRAMES = 12;

const INK = '#15181d';
const BODY = '#2a2f36';
const MUTED = '#8a8f98';

/**
 * True cross-dissolve. The scene BELOW stays fully opaque and only the
 * incoming scene fades 0 -> 1, so there is no dip-to-black at the cut.
 */
const Crossfade: React.FC<{fadeIn: boolean; children: React.ReactNode}> = ({
  fadeIn,
  children,
}) => {
  const frame = useCurrentFrame();
  const opacity = fadeIn
    ? interpolate(frame, [0, XF_FRAMES], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      })
    : 1;
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

/**
 * Each scene is OPAQUE, not a transparent overlay. This is what makes the
 * cross-dissolve work: the outgoing scene stays at full opacity underneath,
 * the incoming one fades 0 -> 1 on top, and by the time the outgoing scene's
 * Sequence ends it is completely covered — so removing it is invisible.
 *
 * With transparent scenes the outgoing content vanishes abruptly instead.
 * Measured 2026-09-01: transparent scenes produced a 57.24 content-diff pop at
 * the frame the hold expired (f221 -> f222), i.e. a near-hard cut.
 */
const Frame: React.FC<{backgroundColor: string; children: React.ReactNode}> = ({
  backgroundColor,
  children,
}) => (
  <AbsoluteFill
    style={{
      backgroundColor,
      fontFamily: FONT,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 110,
    }}
  >
    {children}
  </AbsoluteFill>
);

const TitleScene: React.FC<{
  productName: string;
  tagline?: string;
  accentColor: string;
  backgroundColor: string;
}> = ({productName, tagline, accentColor, backgroundColor}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const pop = spring({
    frame: Math.max(0, frame - 4),
    fps,
    config: {damping: 200},
  });
  const ruleWidth = interpolate(frame, [10, 36], [0, 320], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const taglineIn = interpolate(frame, [16, 38], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <Frame backgroundColor={backgroundColor}>
      <div style={{textAlign: 'center'}}>
        <div
          style={{
            fontSize: 30,
            letterSpacing: 6,
            textTransform: 'uppercase',
            color: MUTED,
            marginBottom: 26,
            opacity: pop,
          }}
        >
          Introducing
        </div>
        <div
          style={{
            fontSize: 150,
            fontWeight: 800,
            color: accentColor,
            lineHeight: 1.02,
            transform: `scale(${0.9 + pop * 0.1})`,
            opacity: pop,
          }}
        >
          {productName}
        </div>
        <div
          style={{
            height: 6,
            width: ruleWidth,
            background: accentColor,
            borderRadius: 3,
            margin: '30px auto',
            boxShadow: `0 0 26px ${accentColor}66`,
          }}
        />
        {tagline ? (
          <div
            style={{
              fontSize: 44,
              color: BODY,
              opacity: taglineIn,
              transform: `translateY(${(1 - taglineIn) * 16}px)`,
              maxWidth: 1400,
              lineHeight: 1.3,
            }}
          >
            {tagline}
          </div>
        ) : null}
      </div>
    </Frame>
  );
};

const FeatureScene: React.FC<{
  productName: string;
  featureList: string[];
  accentColor: string;
  backgroundColor: string;
  screenshotUrl?: string | null;
}> = ({productName, featureList, accentColor, backgroundColor, screenshotUrl}) => {
  const frame = useCurrentFrame();
  const hasShot = Boolean(screenshotUrl);

  // Accent rule under the heading. The feature scene is ~40% of the runtime, so
  // it has to carry real brand colour, not just three bullet dots.
  const ruleWidth = interpolate(frame, [6, 28], [0, 240], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <Frame backgroundColor={backgroundColor}>
      <div
        style={{
          width: '100%',
          maxWidth: 1700,
          display: 'flex',
          flexDirection: 'column',
          gap: 56,
        }}
      >
        <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
          <div style={{fontSize: 60, fontWeight: 700, color: INK}}>
            {`What ${productName} does`}
          </div>
          <div
            style={{
              height: 5,
              width: ruleWidth,
              background: accentColor,
              borderRadius: 3,
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            gap: 70,
            alignItems: 'center',
            justifyContent: hasShot ? 'space-between' : 'center',
          }}
        >
          {/* Always flex: 1 so the column claims the full row width. With
              flex: 0 the column collapsed to content width and the 40px feature
              text wrapped one word per line (visible in the first render —
              "Daily / routines / become / pinball / launches"). The screenshot
              branch is unchanged: 1:1 with the shot. The maxWidth + auto
              margins keep the text in a reading-width column when there is no
              screenshot, so it doesn't stretch edge-to-edge. */}
          <div
            style={{
              flex: 1,
              maxWidth: 1200,
              display: 'flex',
              flexDirection: 'column',
              gap: 30,
              minWidth: 0,
            }}
          >
            {featureList.map((feature, i) => {
              // 22px over 28 frames. The first pass used 28px over 22 frames and
              // peaked at a 27.75 content-diff (measured 2026-09-01) — above the
              // 2-25 "gradual" band, because 40px text moving ~1.3px/frame changes
              // a lot of the masked region every frame. Slower and shorter reads
              // the same but stays in band.
              const itemIn = interpolate(frame, [14 + i * 14, 42 + i * 14], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              });
              return (
                <div
                  // Feature copy is data, not identity — index keys are correct here.
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 22,
                    opacity: itemIn,
                    transform: `translateX(${(1 - itemIn) * -22}px)`,
                  }}
                >
                  {/* Numbered accent chip rather than a 16px dot. Measured
                      2026-09-01: three dots plus the rule gave the feature scene
                      only 0.07% accent coverage against 0.90% (title) and
                      1.61% (cta), which is a real brand-consistency gap in the
                      scene that holds the most runtime. Chips bring it to the
                      same order as the other two scenes. The number comes from
                      the array index, so it stays generic. */}
                  <div
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: 28,
                      background: accentColor,
                      color: '#ffffff',
                      fontSize: 28,
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {i + 1}
                  </div>
                  <div
                    style={{
                      fontSize: 40,
                      color: BODY,
                      lineHeight: 1.25,
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    {feature}
                  </div>
                </div>
              );
            })}
          </div>
          {hasShot ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <Img
                src={staticFile(screenshotUrl as string)}
                style={{
                  width: '100%',
                  borderRadius: 18,
                  display: 'block',
                  boxShadow: '0 18px 50px rgba(0,0,0,0.14)',
                }}
              />
            </div>
          ) : null}
        </div>
      </div>
    </Frame>
  );
};

const CtaScene: React.FC<{
  productName: string;
  accentColor: string;
  backgroundColor: string;
  ctaText: string;
  ctaUrl?: string;
}> = ({productName, accentColor, backgroundColor, ctaText, ctaUrl}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // No start delay: the pill must begin fading in as the crossfade begins,
  // otherwise the incoming scene contributes nothing for the first ~6 frames
  // of its own dissolve (measured: f208 -> f216 content-diff 0.00).
  const pillIn = spring({
    frame,
    fps,
    config: {damping: 200},
  });
  const urlIn = interpolate(frame, [20, 40], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <Frame backgroundColor={backgroundColor}>
      <div style={{textAlign: 'center'}}>
        <div
          style={{
            display: 'inline-block',
            background: accentColor,
            color: '#ffffff',
            fontSize: 54,
            fontWeight: 700,
            padding: '26px 72px',
            borderRadius: 999,
            transform: `scale(${0.92 + pillIn * 0.08})`,
            opacity: pillIn,
            boxShadow: `0 14px 40px ${accentColor}55`,
          }}
        >
          {ctaText}
        </div>
        {ctaUrl ? (
          <div
            style={{
              marginTop: 34,
              fontSize: 38,
              color: MUTED,
              opacity: urlIn,
            }}
          >
            {ctaUrl}
          </div>
        ) : null}
        <div
          style={{
            marginTop: 18,
            fontSize: 30,
            color: MUTED,
            opacity: urlIn * 0.9,
          }}
        >
          {productName}
        </div>
      </div>
    </Frame>
  );
};

export const LaunchTemplate: React.FC<LaunchTemplateProps> = ({
  productName,
  accentColor,
  backgroundColor,
  featureList,
  screenshotUrl = null,
  tagline,
  ctaText,
  ctaUrl,
}) => {
  const {durationInFrames} = useVideoConfig();

  const titleFrames = Math.round(durationInFrames * TITLE_FRACTION);
  const featureFrames = Math.round(durationInFrames * FEATURE_FRACTION);
  const ctaFrames = durationInFrames - titleFrames - featureFrames;

  const cta = ctaText ?? `Get ${productName}`;
  const features = featureList ?? [];

  const solos = [
    {key: 'title', duration: titleFrames},
    {key: 'feature', duration: featureFrames},
    {key: 'cta', duration: ctaFrames},
  ];

  // Each scene except the last is HELD past its solo end so the incoming scene
  // always has a fully-opaque frame underneath to dissolve into.
  //
  // The + 1 matters. The incoming scene's dissolve spans [from, from + XF_FRAMES]
  // and only reaches opacity 1 ON from + XF_FRAMES. The outgoing scene must still
  // be rendered on that exact frame, otherwise the frame before the handoff ends
  // at (XF_FRAMES - 1) / XF_FRAMES opacity and the residual of the outgoing scene
  // disappears in one step. A Sequence covering [from, from + n - 1] therefore
  // needs n = solo + XF_FRAMES + 1, not solo + XF_FRAMES.
  let cursor = 0;
  const positioned = solos.map((scene, i) => {
    const from = cursor;
    cursor += scene.duration;
    const held =
      i < solos.length - 1
        ? scene.duration + XF_FRAMES + 1
        : scene.duration;
    return {...scene, from, held};
  });

  const renderScene = (key: string) => {
    if (key === 'title') {
      return (
        <TitleScene
          productName={productName}
          tagline={tagline}
          accentColor={accentColor}
          backgroundColor={backgroundColor}
        />
      );
    }
    if (key === 'feature') {
      return (
        <FeatureScene
          productName={productName}
          featureList={features}
          accentColor={accentColor}
          backgroundColor={backgroundColor}
          screenshotUrl={screenshotUrl}
        />
      );
    }
    return (
      <CtaScene
        productName={productName}
        accentColor={accentColor}
        backgroundColor={backgroundColor}
        ctaText={cta}
        ctaUrl={ctaUrl}
      />
    );
  };

  return (
    <AbsoluteFill style={{backgroundColor, fontFamily: FONT}}>
      {positioned.map((scene, i) => (
        <Sequence
          key={scene.key}
          from={scene.from}
          durationInFrames={scene.held}
        >
          <Crossfade fadeIn={i > 0}>{renderScene(scene.key)}</Crossfade>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
