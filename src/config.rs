use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct Config {
    /// 监听地址
    pub host: String,
    /// 监听端口
    pub port: u16,
    /// TLS 证书路径 (None 表示不使用 HTTPS)
    pub cert_path: Option<PathBuf>,
    /// TLS 私钥路径
    pub key_path: Option<PathBuf>,
}

impl Config {
    pub fn from_args() -> Self {
        use clap::Parser;

        #[derive(Parser)]
        #[command(name = "keeper")]
        #[command(about = "Keeper 密码管理器后端")]
        struct Args {
            /// 监听地址
            #[arg(short = 'H', long, default_value = "127.0.0.1")]
            host: String,

            /// 监听端口
            #[arg(short, long, default_value = "51000")]
            port: u16,

            /// TLS 证书路径（不提供则使用 HTTP）
            #[arg(long)]
            cert: Option<PathBuf>,

            /// TLS 私钥路径
            #[arg(long)]
            key: Option<PathBuf>,
        }

        let args = Args::parse();

        Config {
            host: args.host,
            port: args.port,
            cert_path: args.cert,
            key_path: args.key,
        }
    }
}
