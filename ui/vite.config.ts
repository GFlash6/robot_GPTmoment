import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],server:{port:5174,proxy:{'/model-test':{target:'http://127.0.0.1:8767',changeOrigin:true},'/api':{target:'http://127.0.0.1:8765',changeOrigin:true}}},preview:{port:4174}});
