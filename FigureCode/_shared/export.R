require_r_packages <- function(packages) {
  missing_packages <- packages[
    !vapply(packages, requireNamespace, logical(1), quietly = TRUE)
  ]
  if (length(missing_packages) > 0L) {
    stop(
      "Missing required R package(s): ",
      paste(missing_packages, collapse = ", "),
      ". Install them with install.packages(c(",
      paste(sprintf("\"%s\"", missing_packages), collapse = ", "),
      ")).",
      call. = FALSE
    )
  }
}

write_json_utf8 <- function(value, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  jsonlite::write_json(
    value,
    path,
    auto_unbox = TRUE,
    pretty = TRUE,
    na = "null"
  )
  invisible(path)
}

sha256_file <- function(path) {
  as.character(digest::digest(file = path, algo = "sha256", serialize = FALSE))
}

export_figure <- function(
  plot,
  output_stem,
  width_mm,
  height_mm,
  dpi = 600,
  formats = c("svg", "pdf", "png", "tiff"),
  font_family = resolve_manuscript_font()
) {
  formats <- unique(tolower(formats))
  unsupported <- setdiff(formats, c("svg", "pdf", "png", "tiff"))
  if (length(unsupported) > 0L) {
    stop("Unsupported export format(s): ", paste(unsupported, collapse = ", "), call. = FALSE)
  }
  require_r_packages(c("svglite", "ragg"))
  dir.create(dirname(output_stem), recursive = TRUE, showWarnings = FALSE)
  width_in <- width_mm / 25.4
  height_in <- height_mm / 25.4
  output_paths <- character()

  if ("svg" %in% formats) {
    path <- paste0(output_stem, ".svg")
    svglite::svglite(path, width = width_in, height = height_in, bg = "white")
    print(plot)
    grDevices::dev.off()
    output_paths <- c(output_paths, path)
  }
  if ("pdf" %in% formats) {
    path <- paste0(output_stem, ".pdf")
    if (capabilities("cairo")) {
      grDevices::cairo_pdf(
        path,
        width = width_in,
        height = height_in,
        family = font_family,
        bg = "white"
      )
    } else {
      grDevices::pdf(
        path,
        width = width_in,
        height = height_in,
        family = "sans",
        bg = "white",
        useDingbats = FALSE
      )
    }
    print(plot)
    grDevices::dev.off()
    output_paths <- c(output_paths, path)
  }
  if ("png" %in% formats) {
    path <- paste0(output_stem, ".png")
    ragg::agg_png(
      path,
      width = width_in,
      height = height_in,
      units = "in",
      res = dpi,
      background = "white"
    )
    print(plot)
    grDevices::dev.off()
    output_paths <- c(output_paths, path)
  }
  if ("tiff" %in% formats) {
    path <- paste0(output_stem, ".tiff")
    ragg::agg_tiff(
      path,
      width = width_in,
      height = height_in,
      units = "in",
      res = dpi,
      background = "white",
      compression = "lzw"
    )
    print(plot)
    grDevices::dev.off()
    output_paths <- c(output_paths, path)
  }
  output_paths
}
