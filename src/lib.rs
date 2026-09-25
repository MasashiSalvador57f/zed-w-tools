use zed_extension_api as zed;

const PREVIEW_SCRIPT: &str = include_str!("../scripts/tategaki_preview.py");
const COMMAND_NAME: &str = "tategaki-preview";

const USAGE: &str =
    "usage: /tategaki-preview <file> [chars=40] [spacing=1.75] [lines=30] [font_size=16] [margin=15]";

/// Entry point of the `w-tools` extension.
struct WToolsExtension;

struct PreviewOptions {
    chars: String,
    spacing: String,
    lines: String,
    font_size: String,
    margin: String,
}

fn parse_options(args: &[String]) -> Result<PreviewOptions, String> {
    let mut opts = PreviewOptions {
        chars: "40".into(),
        spacing: "1.75".into(),
        lines: "30".into(),
        font_size: "16".into(),
        margin: "15".into(),
    };
    for arg in args {
        let Some((key, value)) = arg.split_once('=') else {
            return Err(format!("unknown argument `{arg}`\n{USAGE}"));
        };
        let target = match key {
            "chars" => &mut opts.chars,
            "spacing" => &mut opts.spacing,
            "lines" => &mut opts.lines,
            "font_size" => &mut opts.font_size,
            "margin" => &mut opts.margin,
            _ => return Err(format!("unknown option `{key}`\n{USAGE}")),
        };
        *target = value.to_string();
    }
    Ok(opts)
}

impl zed::Extension for WToolsExtension {
    fn new() -> Self {
        Self
    }

    fn run_slash_command(
        &self,
        command: zed::SlashCommand,
        args: Vec<String>,
        worktree: Option<&zed::Worktree>,
    ) -> Result<zed::SlashCommandOutput, String> {
        match command.name.as_str() {
            COMMAND_NAME => {}
            other => return Err(format!("unknown command `{other}`")),
        }

        let Some(file) = args.first() else {
            return Err(USAGE.into());
        };
        let opts = parse_options(&args[1..])?;
        let worktree = worktree.ok_or("this command must be run inside a worktree")?;

        if !file.starts_with('/') && file.split('/').any(|part| part == "..") {
            return Err("`..` path components are not allowed".into());
        }

        let root = worktree.root_path();
        let abs_src = if file.starts_with('/') {
            file.clone()
        } else {
            format!("{}/{}", root.trim_end_matches('/'), file)
        };
        // Surface a clear error early when the file is not readable.
        if !file.starts_with('/') {
            worktree
                .read_text_file(file)
                .map_err(|e| format!("cannot read `{file}`: {e}"))?;
        }

        let python = worktree
            .which("python3")
            .or_else(|| worktree.which("python"))
            .unwrap_or_else(|| "python3".to_string());

        let output = zed::process::Command::new(python)
            .arg("-c")
            .arg(PREVIEW_SCRIPT)
            .arg(abs_src)
            .arg(opts.chars)
            .arg(opts.spacing)
            .arg(opts.lines)
            .arg(opts.font_size)
            .arg(opts.margin)
            .output()
            .map_err(|e| format!("failed to run python: {e}"))?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        if output.status != Some(0) {
            return Err(format!("preview generation failed: {stderr}"));
        }

        let path = stdout.trim();
        Ok(zed::SlashCommandOutput {
            text: format!("縦書きプレビューをブラウザで開きました: {path}"),
            sections: Vec::new(),
        })
    }
}

zed::register_extension!(WToolsExtension);
