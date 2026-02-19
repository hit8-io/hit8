import { 
  Infinity, Linkedin, ArrowRight, ChevronDown, Eye, ScanEye, 
  RefreshCw, GitBranch, Users, Fingerprint, Target, Trophy, 
  Database, BarChart3, Box, PackageCheck, Mail, Phone
} from 'lucide-react';

import { homeContent } from '../content/home';

const iconMap: Record<string, { bg: JSX.Element; fg: JSX.Element }> = {
  eye: { 
    bg: <Eye className="w-24 h-24 text-white" />, 
    fg: <ScanEye className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
  refresh: { 
    bg: <RefreshCw className="w-24 h-24 text-white" />, 
    fg: <GitBranch className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
  users: { 
    bg: <Users className="w-24 h-24 text-white" />, 
    fg: <Fingerprint className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
  target: { 
    bg: <Target className="w-24 h-24 text-white" />, 
    fg: <Trophy className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
  database: { 
    bg: <Database className="w-24 h-24 text-white" />, 
    fg: <BarChart3 className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
  box: { 
    bg: <Box className="w-24 h-24 text-white" />, 
    fg: <PackageCheck className="w-10 h-10 text-indigo-400 mb-4" /> 
  },
};

export default function Home() {
  const { hero, features } = homeContent;

  return (
    <div className="bg-background text-slate-300 antialiased selection:bg-indigo-500/30 min-h-screen font-sans">
      
      {/* Mystic Background */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-900/20 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-900/20 rounded-full blur-[120px]"></div>
      </div>

      {/* Nav */}
      <nav className="fixed w-full z-50 top-0 border-b border-white/5 bg-background/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Infinity className="text-white w-8 h-8" />
            <span className="text-2xl font-bold text-white tracking-tight">hit<span className="text-indigo-400">8</span></span>
          </div>
          <div className="flex items-center gap-4">
             <a href="https://www.linkedin.com/company/hit8/" target="_blank" rel="noopener noreferrer" className="p-2 text-slate-400 hover:text-white transition-colors">
                <Linkedin className="w-5 h-5" />
            </a>
            <a 
              href={import.meta.env.DEV ? "http://localhost:5173" : "https://iter8.hit8.io"} 
              className="group relative px-6 py-2 rounded-full bg-white/5 border border-white/10 text-sm font-medium text-white hover:bg-white/10 transition-all flex items-center gap-2"
            >
                <span>Client Access</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <header className="relative z-10 min-h-screen flex flex-col justify-center items-center text-center px-6 pt-20">
        <div className="max-w-4xl mx-auto space-y-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs font-medium uppercase tracking-wider mb-4">
                {hero.badge}
            </div>
            <h1 className="text-5xl md:text-7xl font-bold text-white tracking-tight leading-[1.1]">
                {hero.headline} <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">{hero.subHeadline}</span>
            </h1>
            <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
                {hero.description}
            </p>
            <div className="pt-8 animate-bounce">
                <ChevronDown className="w-8 h-8 text-slate-600" />
            </div>
        </div>
      </header>

      {/* Features */}
      <section className="relative z-10 py-32 px-6">
        <div className="max-w-7xl mx-auto">
            <div className="mb-16">
                <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Why hit8?</h2>
                <div className="h-1 w-20 bg-indigo-500 rounded-full"></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {features.map((f: { title: string; description: string; icon: string }, i: number) => (
                    <div key={i} className="group relative p-8 rounded-2xl bg-surface border border-white/5 hover:border-indigo-500/50 transition-all duration-500 hover:shadow-[0_0_30px_-5px_rgba(99,102,241,0.3)] overflow-hidden">
                        <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                            {iconMap[f.icon]?.bg}
                        </div>
                        <div className="relative z-10 h-full flex flex-col justify-end min-h-[200px]">
                            {iconMap[f.icon]?.fg}
                            <h3 className="text-xl font-bold text-white mb-2">{f.title}</h3>
                            <p className="text-slate-400 text-sm leading-relaxed max-h-0 opacity-0 group-hover:max-h-40 group-hover:opacity-100 transition-all duration-500 overflow-hidden">
                                {f.description}
                            </p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
      </section>

      {/* Who We Are */}
      <section className="relative z-10 py-32 px-6 bg-slate-900/50">
        <div className="max-w-7xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-16 text-center">Who We Are</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-12 max-w-4xl mx-auto">
                
                {/* Cedric */}
                <div className="flex flex-col items-center text-center space-y-4">
                    {/* Profile Image Container */}
                    <div className="w-32 h-32 rounded-full border-2 border-indigo-500/30 overflow-hidden bg-slate-800">
                        <img src="/cedric.jpeg" alt="Cedric Caeymaex" className="w-full h-full object-cover" />
                    </div>
                    
                    <div>
                        <div className="flex items-center justify-center gap-2 mb-1">
                            <h3 className="text-2xl font-bold text-white">Cedric Caeymaex</h3>
                            <a href="https://www.linkedin.com/in/cedriccaeymaex/" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-white transition-colors" title="Connect on LinkedIn">
                                <Linkedin className="w-5 h-5" />
                            </a>
                        </div>
                        <p className="text-indigo-400 font-medium mb-4">Market & Client Success</p>
                        <p className="text-slate-400 text-sm max-w-xs mx-auto mb-4">Technology, analytics, and transformation. Bridging strategy with operations.</p>
                        
                        <div className="flex flex-col gap-2 text-sm text-slate-500">
                            <a href="mailto:cedric@hit8.io" className="hover:text-indigo-400 transition-colors flex items-center justify-center gap-2">
                                <Mail className="w-4 h-4" /> cedric@hit8.io
                            </a>
                            <a href="tel:+32478887202" className="hover:text-indigo-400 transition-colors flex items-center justify-center gap-2">
                                <Phone className="w-4 h-4" /> +32 478 88 72 02
                            </a>
                        </div>
                    </div>
                </div>

                {/* Jan */}
                <div className="flex flex-col items-center text-center space-y-4">
                    {/* Profile Image Container */}
                    <div className="w-32 h-32 rounded-full border-2 border-indigo-500/30 overflow-hidden bg-slate-800">
                        <img src="/jan.jpeg" alt="Jan Wilmaers" className="w-full h-full object-cover" />
                    </div>

                    <div>
                        <div className="flex items-center justify-center gap-2 mb-1">
                            <h3 className="text-2xl font-bold text-white">Jan Wilmaers</h3>
                            <a href="https://www.linkedin.com/in/janwilmaers/" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-white transition-colors" title="Connect on LinkedIn">
                                <Linkedin className="w-5 h-5" />
                            </a>
                        </div>
                        <p className="text-indigo-400 font-medium mb-4">Platform & Architecture</p>
                        <p className="text-slate-400 text-sm max-w-xs mx-auto mb-4">Enterprise architecture, complexity reduction, and sustainable change.</p>
                        
                        <div className="flex flex-col gap-2 text-sm text-slate-500">
                            <a href="mailto:jan@hit8.io" className="hover:text-indigo-400 transition-colors flex items-center justify-center gap-2">
                                <Mail className="w-4 h-4" /> jan@hit8.io
                            </a>
                            <a href="tel:+32484953829" className="hover:text-indigo-400 transition-colors flex items-center justify-center gap-2">
                                <Phone className="w-4 h-4" /> +32 484 95 38 29
                            </a>
                        </div>
                    </div>
                </div>

            </div>
        </div>
      </section>

      {/* Footer / Contact */}
      <footer className="relative z-10 py-24 px-6 border-t border-white/5 bg-background">
        <div className="max-w-3xl mx-auto text-center space-y-8">
            <div className="flex items-center justify-center gap-2 mb-8">
                <Infinity className="text-white w-6 h-6" />
                <span className="text-xl font-bold text-white">hit8</span>
            </div>
            
            <h2 className="text-3xl font-bold text-white">Ready for transparency?</h2>
            
            <div className="flex flex-col md:flex-row items-center justify-center gap-4">
                <a href="mailto:info@hit8.io" className="inline-flex items-center gap-2 px-8 py-4 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-all shadow-lg shadow-indigo-500/25">
                    <Mail className="w-5 h-5" />
                    Contact Us
                </a>
                <a href="https://www.linkedin.com/company/hit8/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 px-8 py-4 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 text-white font-semibold transition-all">
                    <Linkedin className="w-5 h-5" />
                    Follow hit8
                </a>
            </div>
            
            <p className="text-slate-500 text-sm pt-12">
                &copy; 2026 Hitloop BV. All rights reserved.
            </p>
        </div>
      </footer>
    </div>
  );
}
