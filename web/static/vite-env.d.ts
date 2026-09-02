declare module '*.jsx?legacy' {
    import type { ComponentType } from 'react';

    const App: ComponentType;
    export default App;
}
