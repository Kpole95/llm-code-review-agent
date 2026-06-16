const { exec } = require("child_process");
 
function pingServer(hostname) {
  exec("ping -c 1 " + hostname, (err, stdout) => {
    if (err) {
      console.error(err);
      return;
    }
    console.log(stdout);
  });
}
