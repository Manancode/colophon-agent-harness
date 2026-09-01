import React from 'react';
import {Composition} from 'remotion';
import brief from '../brief.json';
import {LaunchTemplate} from './GenericLaunch';

/**
 * The brief is the ONLY product-specific input to this project.
 * Field names mirror the the launch-spec format document schema (name, accentColor,
 * backgroundColor, durationInFrames) because that shape is already validated
 * in production — see tools/generic-template-pipeline.md.
 */
type Brief = {
  name: string;
  accentColor: string;
  backgroundColor: string;
  durationInFrames: number;
  fps?: number;
  width?: number;
  height?: number;
  tagline?: string;
  features: string[];
  screenshotUrl?: string | null;
  ctaText?: string;
  ctaUrl?: string;
};

const b = brief as Brief;

export const Root: React.FC = () => {
  return (
    <Composition
      id="LaunchTemplate"
      component={LaunchTemplate}
      durationInFrames={b.durationInFrames}
      fps={b.fps ?? 30}
      width={b.width ?? 1920}
      height={b.height ?? 1080}
      defaultProps={{
        productName: b.name,
        accentColor: b.accentColor,
        backgroundColor: b.backgroundColor,
        featureList: b.features,
        screenshotUrl: b.screenshotUrl ?? null,
        tagline: b.tagline,
        ctaText: b.ctaText,
        ctaUrl: b.ctaUrl,
      }}
    />
  );
};
