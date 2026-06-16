function renderComment(comment) {
  const container = document.getElementById("comments");
  container.innerHTML += "<p>" + comment.text + "</p>";
}
