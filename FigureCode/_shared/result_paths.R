# Resolve original provenance without changing the saved historical record.
relocated_result_path <- function(root, value) {
  record <- jsonlite::fromJSON(file.path(root,'result/figure_data/_metadata/manifest.json'),simplifyVector=FALSE)
  records <- c(record$storage_migration$paths,record$layout_cleanup$paths,record$code_layout$paths)
  records <- records[order(vapply(records,function(p)nchar(p[[1]]),integer(1)),decreasing=TRUE)]
  for (i in seq_len(8)) {
    previous <- value
    for (p in records) if (value == p[[1]] || startsWith(value,paste0(p[[1]],'/'))) {
      value <- paste0(p[[2]],substring(value,nchar(p[[1]])+1)); break
    }
    if (value == previous) break
  }
  file.path(root,value)
}
