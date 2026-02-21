import { Infinity as InfinityIcon, Linkedin, ArrowRight } from 'lucide-react'
import { styles } from '../lib/styles'

export default function HomeSkeleton() {
  return (
    <div className={styles.pageContainer}>
      {/* Mystic Background */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-900/20 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-900/20 rounded-full blur-[120px]"></div>
      </div>

      {/* Nav */}
      <nav className="fixed w-full z-50 top-0 border-b border-white/5 bg-background/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <InfinityIcon className="text-white w-8 h-8" />
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

      {/* Hero Section Skeleton */}
      <header className="relative z-10 min-h-screen flex flex-col justify-center items-center text-center px-6 pt-20">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs font-medium uppercase tracking-wider mb-4">
            <div className="h-4 w-32 bg-indigo-500/30 rounded animate-pulse"></div>
          </div>
          
          <h1 className="text-5xl md:text-7xl font-bold text-white tracking-tight leading-[1.1]">
            <div className="h-16 md:h-24 w-full bg-white/10 rounded animate-pulse mb-4"></div>
            <div className="h-16 md:h-24 w-3/4 mx-auto bg-indigo-500/20 rounded animate-pulse"></div>
          </h1>
          
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
            <div className="h-6 w-full bg-slate-700/30 rounded animate-pulse mb-2"></div>
            <div className="h-6 w-5/6 mx-auto bg-slate-700/30 rounded animate-pulse"></div>
          </p>
        </div>
      </header>

      {/* Features Section Skeleton */}
      <section className="relative z-10 py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Why hit8?</h2>
            <div className="h-1 w-20 bg-indigo-500 rounded-full"></div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, idx) => (
              <div key={idx} className="group relative p-8 rounded-2xl bg-surface border border-white/5 overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-10">
                  <div className="w-24 h-24 bg-white/10 rounded animate-pulse"></div>
                </div>
                <div className="relative z-10 h-full flex flex-col justify-end min-h-[200px]">
                  <div className="w-10 h-10 bg-indigo-500/20 rounded mb-4 animate-pulse"></div>
                  <div className="h-6 w-3/4 bg-white/10 rounded mb-2 animate-pulse"></div>
                  <div className="h-4 w-full bg-slate-700/20 rounded animate-pulse"></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
