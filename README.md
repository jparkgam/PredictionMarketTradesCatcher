# PredictionMarketTradesCatcher
This file was created for a CSC 433 project at NCSU.

This is the code that lets me get data from the Kalshi /markets/trades endpoint. This gives us info on individual trade #s, the price bought, the position taken, and volume of contracts for each trade.

This file does NOT currently get info from a specific endpoint--I suspect that endpoint is currently broken, or Kalshi forgot to update it properly on their website. To get a specific market, you'd have to modify this file to use the /markets/{ticker}/trades endpoint. This isn't a matter of authentication; I've proven that my auth works, it's just the specific endpoint messing up.

Notes: You'll have to get an API key from Kalshi to run this program. To do this, follow these steps: 
<img width="943" height="560" alt="APIsteps" src="https://github.com/user-attachments/assets/694290e4-a4e9-4a61-9e05-5cdeae280b3c" />

Once you've done that, you can replace the RSA_SIG_PATH value in the attached file with the filename of your RSA key, and the MY_API_KEY value with your actual key. From there, read the program's instructions at the top of the file for arguments on how to run it.
