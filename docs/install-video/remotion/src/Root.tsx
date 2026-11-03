import React from 'react';
import {Composition} from 'remotion';
import {Terminal} from './Terminal';
import {FPS, scenes, sceneFrames} from './scenes';

export const Root: React.FC = () => (
  <>
    {scenes.map((scene) => (
      <Composition
        key={scene.id}
        id={scene.id}
        component={() => <Terminal scene={scene} />}
        durationInFrames={sceneFrames(scene)}
        fps={FPS}
        width={1920}
        height={1080}
      />
    ))}
  </>
);
