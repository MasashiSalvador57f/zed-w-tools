use zed_extension_api as zed;

/// Entry point of the `w-tools` extension.
///
/// Zed instantiates this struct once when the extension is loaded.
/// Add capabilities (language servers, slash commands, context servers, ...)
/// by implementing the corresponding methods of [`zed::Extension`].
struct WToolsExtension;

impl zed::Extension for WToolsExtension {
    fn new() -> Self {
        Self
    }
}

zed::register_extension!(WToolsExtension);
