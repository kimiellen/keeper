use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct Config {
    /// 监听地址
    pub host: String,
    /// 监听端口
    pub port: u16,
    /// 配置目录路径（存放 databases.json）
    pub config_dir: Option<PathBuf>,
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

            /// 配置目录路径（存放 databases.json，默认使用系统数据目录）
            #[arg(short = 'c', long)]
            config_dir: Option<PathBuf>,
        }

        let args = Args::parse();

        Config {
            host: args.host,
            port: args.port,
            config_dir: args.config_dir,
        }
    }
}
