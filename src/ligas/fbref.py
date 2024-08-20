from pathlib import Path
import os
import random
from typing import Sequence, List, Dict
import requests
from bs4 import BeautifulSoup
import threading
import time 

from .exceptions import FbrefRequestException, FbrefRateLimitException, FbrefInvalidLeagueException
from .entity_config import Head2Head, SeasonUrls,CurrentSeasonUrls, TopScorers, BestScorer
from .utils import compositions
from .utils import browserHeaders
from .utils import browser

from .logger import logger



class fbref():
    def __init__(self, wait_time :int =5) -> None:
        self.wait_time = wait_time
        webBrowser = random.choice(browser)
        self.header = browserHeaders.get(webBrowser)

    def _get(self, url : str) -> requests.Response:

        """
            call _get create an instance of requests
            Args:
                url (str): is the the endpoint of fbref website 
            Returns:
                object (requests.Response): return the response
        """
       
        
        response = requests.get(url=url, headers=self.header)
        wait_thread = threading.Thread(target=self._wait)
        wait_thread.start()

        status = response.status_code

        if status == 429:
            raise FbrefRateLimitException()
 
        if status in set([404, 504]) :
            raise  FbrefRequestException()
        
        return response
    
    def _wait(self):
        """
            Defining a waiting time for avoid rate limit 
        """
        time.sleep(self.wait_time)
    
    # ====================================== get_current_seasons ==========================================#
    def get_valid_seasons(self, league: str) -> SeasonUrls:
        """
        Retrieves all valid years and their corresponding URLs for a specified competition.

        Args:
            league : str
                The league for which to obtain valid seasons. Examples include "EPL" and "La Liga". 
                For a full list of options, import `compositions` from the FBref module and check the keys.

        Returns:
            Season and URLs : SeasonUrls[dict]
                A dictionary in the format {year: URL, ...}, where URLs should be prefixed with "https://fbref.com" to form a complete link.
        """

        if not isinstance(league, str):
            raise  TypeError('`league` must be a str eg: Champions League .')
        
        validLeagues = [league for league in compositions.keys()]

        if league not in validLeagues:
            raise FbrefInvalidLeagueException(league, 'FBref', validLeagues)

        url = compositions[league]['history url']
        r = self._get(url)
        soup = BeautifulSoup(r.content, 'html.parser')

        seasonUrls = dict([
            (x.text, x.find('a')['href'])
            for x in soup.find_all('th', {'data-stat': True, 'class': True})
            if x.find('a') is not None
        ])

        return SeasonUrls(seasonUrls)
    
    def getCurrentSeasons(self, league: str) -> CurrentSeasonUrls:
        
        """
            year , ligue stats link
        """
        
        return NotImplementedError
    
    def get_top_scorers(self, league: str) -> dict:
        """
        Retrieves the top scorer's statistics for a given league and season.

        Args:
            league (str): 
                The league identifier for which to obtain TopScorers.
                Examples include "EPL" (English Premier League) and "La Liga" (Spain's top division).
            currentSeason (str): 
                The season for which to retrieve the top scorer's statistics.
                The format is typically "YYYY-YYYY", e.g., "2023-2024".

        Returns:
            dict: 
                A dictionary containing the following keys:
                - 'top_scorer': The name of the top scorer.
                - 'goals': The number of goals scored by the top scorer.
                - 'stats_link': The direct link to the detailed statistics of the top scorer.
                - 'club': The club the top scorer played for during that season.
                - 'top_scorer_link': The link to the player's profile on the website.

        Raises:
            ValueError: If no data is found for the given league and season.
            TypeError: If the required table is not found on the page.
            """
        if not isinstance(league, str):
           raise  TypeError('`league` must be a str eg: Champions League .')
        
        validLeagues = [league for league in compositions.keys()]
       
        if league not in validLeagues:
           raise FbrefInvalidLeagueException(league, 'FBref', validLeagues)

        url = compositions[league]['history url']
        r = self._get(url)
        soup = BeautifulSoup(r.content, 'html.parser')
        # Find all rows (tr) corresponding to a season
        rows = soup.find_all('tr')

        top_scorers = {
                f'{league} season {row.find("th", {"data-stat": "year_id"}).text.strip()}': {
                    'year': row.find("th", {"data-stat": "year_id"}).text.strip(),
                    'top_scorer': row.find('td', {'data-stat': 'top_scorers'}).find('a').text.strip(),
                    'goals': row.find('td', {'data-stat': 'top_scorers'}).find('span').text.strip(),
                    'stats_link': "https://fbref.com" + row.find('td', {'data-stat': 'top_scorers'}).find('a')['href'],
                    'club': row.find('td', {'data-stat': 'champ'}).text.split('-')[0].strip() if row.find('td', {'data-stat': 'champ'}) else "Unknown"
                }
                for row in soup.find_all('tr')
                if row.find('td', {'data-stat': 'top_scorers'}) and row.find('td', {'data-stat': 'top_scorers'}).find('a')
            }
        return top_scorers

    def topScorer(self, league: str, currentSeason: str) -> dict:
        """
        Scrapes the best scorer's statistics for a specified league and season.

        Args:
            league (str): The league identifier (e.g., "EPL", "La Liga").
            currentSeason (str): The season to retrieve (e.g., "2023-2024").

        Returns:
            dict: A dictionary containing the top scorer's name, goals, stats link, and club.

        Raises:
            ValueError: If no data is found for the given league and season.
            TypeError: If the stats table is not found on the page.
        """
        # Fetch the top scorers data for the given league
        response = self.get_top_scorers(league=league)
        key = f'{league} season {currentSeason}'

        # Check if the season data exists
        if key in response:
            stats_link = response[key]['stats_link']
            
            # Fetch and parse the top scorer's stats page
            r = requests.get(stats_link)
            if r.status_code != 200:
                raise ConnectionError(f"Failed to retrieve data from {stats_link}")

            soup = BeautifulSoup(r.content, 'html.parser')
            table = soup.find('table', {'id': 'scout_summary_FW'})

            if not table:
                raise TypeError("The statistics table was not found on the page.")

            # Extract statistics using list comprehension
            stats = [
                {
                    'statistic': row.find('th', {'data-stat': 'statistic'}).text.strip(),
                    'per90': row.find('td', {'data-stat': 'per90'}).text.strip(),
                    'percentile': row.find('td', {'data-stat': 'percentile'}).text.strip()
                }
                for row in table.find_all('tr')[1:]  # Skip the header row
            ]

            # Return the extracted data in a structured dictionary
            return {
                'top_scorer': response[key]['top_scorer'],
                'goals': response[key]['goals'],
                'stats_link': stats_link,
                'club': response[key]['club'],
                'detailed_stats': stats
            }

        else:
            # Raise an error if no data is found for the given season
            raise ValueError(f"No data found for the {currentSeason} season.")
